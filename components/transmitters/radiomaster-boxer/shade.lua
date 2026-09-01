-- SHADE VTOL telemetry page
-- Flight mode as text (read from CH6 / S3 6-position) plus the values that
-- matter in flight. The mode comes from the channel, not from CRSF telemetry,
-- so it stays correct even though the FC speaks MAVLink rather than CRSF.
--
-- Layout is sized for the Boxer's 128x64 mono LCD and follows the stock
-- telemetry pages: a mode banner, then two columns of labelled rows. Each row
-- is a small label on the left and the value right-aligned to a fixed column
-- edge, so a digit appearing or dropping never shifts anything sideways.

local MODES = {
  {-1024, -700, "STAB"},
  { -700, -350, "ALT"},
  { -350,    0, "POS"},
  {    0,  350, "POS"},
  {  350,  700, "MISN"},
  {  700,  1025, "RTL"},
}

local function modeText()
  local v = getValue("ch6")
  if v == nil then return "---" end
  for _, m in ipairs(MODES) do
    if v >= m[1] and v < m[2] then return m[3] end
  end
  return "?"
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
  centred(1, 1, modeText(), MID_W, MIDSIZE + INVERS)
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
