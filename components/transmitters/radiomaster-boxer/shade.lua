-- SHADE VTOL telemetry page
-- Flight mode as text (read from CH6) plus the values that matter in flight.
-- The mode comes from the channel, not from CRSF telemetry, so it stays
-- correct even though the FC speaks MAVLink rather than CRSF.
--
-- Layout is sized for the Boxer's 128x64 mono LCD and follows the stock
-- telemetry pages: a mode banner, then two columns of labelled rows. Each row
-- is a small label on the left and the value right-aligned to a fixed column
-- edge, so a digit appearing or dropping never shifts anything sideways.

-- CH6 carries the flight mode. SB (3-position) sets it on its own, and an
-- SC + SF latch replaces the channel outright for the two auto modes. There
-- is no 6-position rotary on this radio, so only five of the six PX4 slots
-- are reachable:
--
--   SC up   + SF    988us   slot 1   Mission (COM_FLTMODE1=3)
--   SB up          1173us   slot 2   Stabilized
--   SB middle      1347us   slot 3   Altitude
--   SB down        1520us   slot 4   Position
--   SC down + SF   2011us   slot 6   RTL
--
-- Slot 5 (also Position) cannot be reached and is left out.
--
-- Slot 1 reads MISN. COM_FLTMODE1 was 4 (Hold) until 2026-09-09, when it was
-- set back to 3 (Mission) on the aircraft -- see FC_CHANGELOG.md. The value
-- list lives in the generated metadata at
-- build/px4_fmu-v6c_default/generated_params/module_params.c: 3 is Mission,
-- 4 is Hold. Read the aircraft before trusting this line; the banner has to
-- say what the aircraft will actually do.
--
-- The boundaries below are PX4's own slot edges rather than midpoints between
-- the readings, so the banner changes exactly when the FC changes mode. PX4
-- splits the channel at slot_min -1.05, slot_max +1.05 and slot_width_half
-- 1/6 (rc_update.cpp), which with RC6_MIN/MAX/TRIM at 1000/2000/1500 puts the
-- edges at 1107, 1282, 1457, 1632 and 1807us. getValue returns EdgeTX units,
-- where 1000/1500/2000us map to -1024/0/+1024, hence the values used here.
--
-- The readings above are measured (2026-09-09, RC_CHANNELS against HEARTBEAT).
-- The narrowest margin to an edge is 63us, so no slot sits near a boundary.
-- Should a calibration or mix change move a reading across an edge the banner
-- follows the FC rather than the switch label, which is the intent: the screen
-- shows what the aircraft will do, not what the switch is called.
-- The two latched readings sit slightly outside the nominal -1024..+1024, so
-- the outer bounds are opened rather than clipped: 988us measures -1049 and
-- 2011us measures +1047, and a value falling off either end would print "?".
local MODES = {
  {-2048, -805, "MISN"},
  { -805, -447, "STAB"},
  { -447,  -88, "ALT"},
  {  -88,  270, "POS"},
  {  270,  629, "POS"},
  {  629, 2048, "RTL"},
}

-- SE (2-position) drives the kill switch on CH9. PX4 arms it above
-- RC_KILLSWITCH_TH, which is 0.75 -- three quarters of the way from centre to
-- full, so 1750us, which is +512 in EdgeTX units. Down is 2000us on this
-- radio, so flipping SE down kills.
--
-- getValue reads the radio's own mixer output, so CH9 is here whether or not
-- the aircraft is listening -- this says the switch is down, not that the
-- motors are actually cut. The web HUD answers the other question from the
-- FC's own HEARTBEAT; a telemetry script has no such channel to ask.
--
-- A nil still means the model has no CH9 mixed at all, and then the banner
-- keeps showing the flight mode rather than inventing a kill.
local KILL_CH = "ch9"
local KILL_ON = 512

local function killed()
  local v = getValue(KILL_CH)
  if v == nil then return false end
  return v > KILL_ON
end

local function modeText()
  local v = getValue("ch6")
  if v == nil then return "---" end
  for _, m in ipairs(MODES) do
    if v >= m[1] and v < m[2] then return m[3] end
  end
  return "?"
end

-- The motors are cut, so which flight mode the switches ask for no longer
-- describes anything the aircraft is doing. KILL takes the banner outright
-- rather than competing for the 64px column.
local function bannerText()
  if killed() then return "KILL" end
  return modeText()
end

-- Telemetry values arrive by name; a missing sensor reads back as nil or 0.
local function val(name)
  local v = getValue(name)
  if v == nil then return nil end
  if type(v) == "table" then return nil end
  return v
end

-- ---------------------------------------------------------------------------
-- eph (GPS horizontal accuracy) -- read from the raw CRSF passthrough frame.
--
-- eph has no field in the CRSF GPS sensor frame (crsf_protocol.h: latitude,
-- longitude, groundspeed, gps_heading, altitude, satellites_in_use), so
-- getValue("...") can never see it -- there is no sensor to register.
--
-- The TX does send it, though. Alongside every GPS_RAW_INT it emits an
-- ArduPilot passthrough frame carrying appid 0x5002, which packs eph into
-- bits 6..14 (MAVLink.cpp: ap_send_crsf_passthrough_single(0x5002,
-- format_gps_status(fix_type, alt, eph, sats))). That frame reaches us as
-- CRSF_FRAMETYPE_ARDUPILOT_RESP (0x80), which crossfireTelemetryPop() hands
-- over verbatim -- it filters nothing.
--
-- 🔴 Popping is destructive and the queue is shared. Anything we take here is
--    gone for every other script, so pop only while this page is on screen
--    and put nothing back.
local ARDUPILOT_RESP = 0x80
local AP_SINGLE      = 0xF0   -- sub_type: one appid/data pair
local AP_MULTI       = 0xF2   -- sub_type: count, then that many pairs
local APPID_GPS      = 0x5002

local ephDm = nil             -- last eph in decimetres, nil until one arrives

-- Undo prep_number(value, digits=2, power=1) from
-- ardupilot_custom_telemetry.cpp: 7 bits of mantissa, low bit says whether to
-- multiply by 10, bit 8 is the sign. eph is never negative but the sign bit is
-- decoded anyway so a garbled frame cannot read as a huge positive number.
-- 🔴 Plain arithmetic, no bit32. bit32 is a Lua 5.2 library and whether a
--    given EdgeTX build compiles it in is not something this script can rely
--    on -- a missing bit32 would be a nil-index error at the first redraw, on
--    the radio, in the field. Shifts are exact in doubles at these widths.
local function rshift(v, n) return math.floor(v / (2 ^ n)) end
local function band(v, mask) return v % (mask + 1) end   -- mask must be 2^k-1

-- prep_number(value, digits=2, power=1) inverted: 7 bits of mantissa with the
-- low bit saying "x10". The producer's 9th bit is a sign, but we never read
-- it -- see below.
local function unprep21(v)
  local mant = rshift(v, 1)
  if v % 2 == 1 then return mant * 10 end
  return mant
end

-- Bits 6..13 of the 0x5002 payload.
--
-- 🔴 Eight bits, not nine. format_gps_status() writes the eph field at offset
--    6 and the advanced-fix status at offset 14, so prep_number's 9th bit
--    (its sign) and advstatus bit 0 are the same bit. advstatus is non-zero
--    exactly when fix_type > 3 -- which is every RTK fix, what this aircraft
--    flies on -- and reading nine bits then decodes that as "negative",
--    turning eph 0.14m into -0.1m. eph is a distance and never negative, so
--    drop the overlapping bit and take eight.
local function ephFromGpsStatus(data)
  return unprep21(band(rshift(data, 6), 0xFF))
end

-- Little-endian reads. crossfireTelemetryPop gives a 1-based byte table.
local function u16(p, i)
  if p[i] == nil or p[i + 1] == nil then return nil end
  return p[i] + p[i + 1] * 256
end

local function u32(p, i)
  if p[i] == nil or p[i + 3] == nil then return nil end
  return p[i] + p[i + 1] * 256 + p[i + 2] * 65536 + p[i + 3] * 16777216
end

-- Drain whatever has queued since the last redraw. Several frames can pile up
-- between draws, so keep the newest 0x5002 rather than stopping at the first.
-- The bound is a guard against a busy queue starving the draw, not a count of
-- anything meaningful.
local function pollEph()
  for _ = 1, 8 do
    local cmd, packet = crossfireTelemetryPop()
    if cmd == nil then return end
    if cmd == ARDUPILOT_RESP and packet ~= nil then
      local sub = packet[1]
      if sub == AP_SINGLE then
        if u16(packet, 2) == APPID_GPS then
          local d = u32(packet, 4)
          if d ~= nil then ephDm = ephFromGpsStatus(d) end
        end
      elseif sub == AP_MULTI then
        -- sub_type, count, then count x (appid u16, data u32)
        local count = packet[2] or 0
        for n = 0, count - 1 do
          local base = 3 + n * 6
          if u16(packet, base) == APPID_GPS then
            local d = u32(packet, base + 2)
            if d ~= nil then ephDm = ephFromGpsStatus(d) end
          end
        end
      end
    end
  end
end

-- %d rejects a non-integer outright on newer Lua, and the decimal sensors can
-- hand us one at any moment, so round before formatting.
local function whole(v)
  return string.format("%d", (v >= 0) and math.floor(v + 0.5) or -math.floor(-v + 0.5))
end

-- Every value is padded to three characters.
--
-- Values are right-aligned to VALUE_R, so their left edge moves with the
-- character count: "3.4" starts 8px further left than "75", and a bare "9"
-- 8px further right again. Read down the page that put Sat one cell right of
-- Cur/Spd and Eph one cell left of Bat/Alt -- close enough to look like a
-- mistake, far enough to make the eye re-find the number on every row.
--
-- Three is the width the decimal readings already need (Cur, Spd, Eph), so
-- padding the integers to match lines all six values up at the same left
-- edge. A four-character reading (a 1000+ altitude, eph past 10m) still
-- right-aligns from there and simply extends one cell further left.
local function pad3(s)
  while #s < 3 do s = " " .. s end
  return s
end

-- Curr, GSpd, Temp and RxBt carry prec: 1 in the model. Printing those as
-- plain integers rounds a 3.4A hover draw down to "3" and anything under 1A
-- to a flat "0", which reads as a dead sensor. Show the decimal while the
-- value is small enough to need it and drop it once the whole number carries
-- the information.
local function fmt(v)
  if v == nil then return pad3("--") end
  if v > -10 and v < 10 then return string.format("%.1f", v) end
  return pad3(whole(v))
end

-- Sensors that are whole numbers to begin with never get a decimal.
-- Sensors that are whole numbers to begin with never get a decimal.
local function fmtInt(v)
  if v == nil then return pad3("--") end
  return pad3(whole(v))
end

-- Geometry. The default font is 8x8, MIDSIZE 8x12. The banner is one 14px
-- row; three label/value rows of 16px fill the 50px below it with two pixels
-- to spare, which leaves each row a little breathing space.
--
-- Labels use the default font rather than SMLSIZE to stay readable in the
-- air, which costs 3px per character. Three-letter labels keep the widest
-- reading (a four-digit altitude) clear of them: 24px of label plus 32px of
-- value still fits the 64px column.
local COL_W    = 64
local BANNER_H = 14
local ROW_H    = 16
local MID_W    = 8   -- MIDSIZE, used for values
local LABEL_W  = 8   -- default font, used for labels
local SML_W    = 5   -- SMLSIZE, the fallback when a value runs wide
local BIG_W    = 16  -- DBLSIZE, used for the mode banner
local LABEL_X  = 1   -- label starts here, inside its column
local VALUE_R  = 62  -- values end here, inside its column

-- One labelled row: label pinned left, value right-aligned to VALUE_R. An
-- unusually wide reading (a five-character altitude such as -1500) would run
-- back into the label, so the label shrinks for that row rather than letting
-- the two overlap.
local function row(col, n, label, text)
  local x0 = (col - 1) * COL_W
  local y  = BANNER_H + (n - 1) * ROW_H
  local vx = VALUE_R - #text * MID_W

  local lw, ly = LABEL_W, y + 4
  local flags = 0
  if LABEL_X + #label * lw + 2 > vx then
    lw, ly, flags = SML_W, y + 5, SMLSIZE
  end

  -- The value is 12px tall in a 16px row, so nudge it down to sit centred;
  -- the label drops a little further to share its baseline.
  lcd.drawText(x0 + LABEL_X, ly, label, flags)
  lcd.drawText(x0 + vx, y + 2, text, MIDSIZE)
end

-- Text centred inside one of the two columns, at the given font width.
local function centred(col, y, text, w, flags)
  lcd.drawText((col - 1) * COL_W + math.floor((COL_W - #text * w) / 2), y, text, flags)
end

-- eph in metres, always to one decimal. The decoded value is decimetres, so
-- the tenth is exactly what the link carries -- rounding it away above 10m
-- would drop the only digit that separates a 12.4m fix from a 12m one, and a
-- fixed width keeps the value from jittering sideways as it crosses 10.
local function fmtEph()
  if ephDm == nil then return pad3("--") end
  return string.format("%.1f", ephDm / 10)
end

local function run(event)
  lcd.clear()
  pollEph()

  -- Banner: flight mode centred in the left column, link quality in the
  -- right, both inverted so the row reads as one bar.
  lcd.drawFilledRectangle(0, 0, LCD_W, BANNER_H, SOLID)
  centred(1, 1, bannerText(), MID_W, MIDSIZE + INVERS)
  centred(2, 1, fmtInt(val("RQly")), MID_W, MIDSIZE + INVERS)

  row(1, 1, "Cur", fmt(val("Curr")))
  row(2, 1, "Bat", fmtInt(val("Bat%")))

  row(1, 2, "Spd", fmt(val("GSpd")))
  row(2, 2, "Alt", fmtInt(val("GAlt")))

  -- Sat and Eph share the bottom row: the count on the left where Tmp's
  -- neighbour used to be, the accuracy on the right in the slot Tmp left.
  -- They belong side by side -- 21 satellites with eph 6m is still a bad fix,
  -- and the count on its own would say the opposite.
  row(1, 3, "Sat", fmtInt(val("Sats")))
  row(2, 3, "Eph", fmtEph())

  -- Column divider, drawn last so it sits on top of nothing important.
  lcd.drawLine(COL_W - 1, BANNER_H, COL_W - 1, LCD_H - 1, DOTTED, FORCE)

  return 0
end

return {run = run}
