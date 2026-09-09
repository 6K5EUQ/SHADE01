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

-- %d rejects a non-integer outright on newer Lua, and the decimal sensors can
-- hand us one at any moment, so round before formatting.
local function whole(v)
  return string.format("%d", (v >= 0) and math.floor(v + 0.5) or -math.floor(-v + 0.5))
end

-- Curr, GSpd, Temp and RxBt carry prec: 1 in the model. Printing those as
-- plain integers rounds a 3.4A hover draw down to "3" and anything under 1A
-- to a flat "0", which reads as a dead sensor. Show the decimal while the
-- value is small enough to need it and drop it once the whole number carries
-- the information.
local function fmt(v)
  if v == nil then return "--" end
  if v > -10 and v < 10 then return string.format("%.1f", v) end
  return whole(v)
end

-- Sensors that are whole numbers to begin with never get a decimal.
local function fmtInt(v)
  if v == nil then return "--" end
  return whole(v)
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

local function run(event)
  lcd.clear()

  -- Banner: flight mode centred in the left column, link quality in the
  -- right, both inverted so the row reads as one bar.
  lcd.drawFilledRectangle(0, 0, LCD_W, BANNER_H, SOLID)
  centred(1, 1, bannerText(), MID_W, MIDSIZE + INVERS)
  centred(2, 1, fmtInt(val("RQly")), MID_W, MIDSIZE + INVERS)

  row(1, 1, "Cur", fmt(val("Curr")))
  row(2, 1, "Bat", fmtInt(val("Bat%")))

  row(1, 2, "Spd", fmt(val("GSpd")))
  row(2, 2, "Alt", fmtInt(val("GAlt")))

  row(1, 3, "Tmp", fmt(val("Temp")))
  row(2, 3, "Sat", fmtInt(val("Sats")))

  -- Column divider, drawn last so it sits on top of nothing important.
  lcd.drawLine(COL_W - 1, BANNER_H, COL_W - 1, LCD_H - 1, DOTTED, FORCE)

  return 0
end

return {run = run}
