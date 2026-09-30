{ USERHDD - user-defined hard disk (Setup type 1) for the NCR System 3230
  486 BIOS 517-0000672 v2.03.00. Replacement for NCR's lost USERHDD.EXE.

  Build (MS-DOS):  ppcross8086 -Tmsdos -WmSmall -Cp8086 userhdd.pas
  Build (test):    ppc386 -dSIMCMOS userhdd.pas   (CMOS simulated in CMOS.BIN)

  What the BIOS expects (from the disassembly):
    POST F000:3C58 copies CMOS 72h-7Bh into the type-1 slot of the drive
    table (F000:E401) when drive C or D is type 1 and CMOS 7Ch equals the low
    byte of the 16-bit sum of 72h-7Bh (sum must not be 0).
    Setup FA40:1227 refuses type 1 unless that same check passes.

    CMOS 72h/73h cylinders      75h/76h write precomp (FFFFh = none)
    CMOS 74h     heads          77h     max ECC burst (unused, 0)
    CMOS 78h     control byte   79h/7Ah landing zone
                 (bit 3 = more than 8 heads)
    CMOS 7Bh     sectors/track  7Ch     checksum

    Drive types: CMOS 12h high nibble = C:, low nibble = D:
    (0Fh = extended type in 19h/1Ah). Standard checksum: 16-bit sum of
    10h-2Dh stored in 2Eh (high) / 2Fh (low). }

program UserHdd;

{$mode tp}
{$ifndef SIMCMOS}
{$asmmode intel}
{$endif}

const
  Version = '1.0';
  RegTable = $72;
  RegTableSum = $7C;
  RegTypes = $12;
  RegCsumHi = $2E;
  RegCsumLo = $2F;

type
  TGeom = record
    Cyl, Heads, Spt, Wpc, Lz: Word;
  end;

var
  ForceRun, AssumeYes, WantSlave: Boolean;
  SetDrive: Char;        { ' ', 'C' or 'D' }

{ ---------------------------------------------------------------- CMOS I/O }

{$ifdef SIMCMOS}
var
  Sim: array[0..127] of Byte;

procedure SimLoad;
var f: file; n: Word;
begin
  Assign(f, 'CMOS.BIN');
  {$I-} Reset(f, 1); {$I+}
  if IOResult <> 0 then
  begin
    WriteLn('Simulation: CMOS.BIN not found.');
    Halt(3);
  end;
  BlockRead(f, Sim, 128, n);
  Close(f);
end;

procedure SimSave;
var f: file;
begin
  Assign(f, 'CMOS.BIN');
  Rewrite(f, 1);
  BlockWrite(f, Sim, 128);
  Close(f);
end;

function CmosRead(Reg: Byte): Byte;
begin
  CmosRead := Sim[Reg and $7F];
end;

procedure CmosWrite(Reg, Value: Byte);
begin
  Sim[Reg and $7F] := Value;
  SimSave;
end;
{$else}
function CmosRead(Reg: Byte): Byte; assembler;
asm
  pushf
  cli
  mov al, Reg
  out 70h, al
  jmp @d1
@d1:
  in al, 71h
  popf
end;

procedure CmosWrite(Reg, Value: Byte); assembler;
asm
  pushf
  cli
  mov al, Reg
  out 70h, al
  jmp @d1
@d1:
  mov al, Value
  out 71h, al
  popf
end;
{$endif}

{ ------------------------------------------------------------ table helpers }

function TableSum: Word;
var r: Byte; s: Word;
begin
  s := 0;
  for r := RegTable to RegTable + 9 do
    s := s + CmosRead(r);
  TableSum := s;
end;

function TableValid: Boolean;
var s: Word;
begin
  s := TableSum;
  TableValid := (s <> 0) and (Lo(s) = CmosRead(RegTableSum));
end;

procedure ReadTable(var g: TGeom);
begin
  g.Cyl := CmosRead($72) or (Word(CmosRead($73)) shl 8);
  g.Heads := CmosRead($74);
  g.Wpc := CmosRead($75) or (Word(CmosRead($76)) shl 8);
  g.Lz := CmosRead($79) or (Word(CmosRead($7A)) shl 8);
  g.Spt := CmosRead($7B);
end;

function MainSum: Word;
var r: Byte; s: Word;
begin
  s := 0;
  for r := $10 to $2D do
    s := s + CmosRead(r);
  MainSum := s;
end;

function MainValid: Boolean;
begin
  MainValid := MainSum = (Word(CmosRead(RegCsumHi)) shl 8) or CmosRead(RegCsumLo);
end;

function DriveType(Drive: Char): Integer;
var t: Byte;
begin
  t := CmosRead(RegTypes);
  if Drive = 'C' then
  begin
    t := t shr 4;
    if t = $F then t := CmosRead($19);
  end
  else
  begin
    t := t and $F;
    if t = $F then t := CmosRead($1A);
  end;
  DriveType := t;
end;

function SizeMB(const g: TGeom): LongInt;
begin
  SizeMB := (LongInt(g.Cyl) * g.Heads * g.Spt) div 2048;
end;

procedure PrintGeom(const g: TGeom);
begin
  Write(g.Cyl, ' cylinders, ', g.Heads, ' heads, ', g.Spt, ' sectors/track = ',
        SizeMB(g), ' MB');
  if g.Wpc = $FFFF then Write(', precomp none')
  else Write(', precomp ', g.Wpc);
  WriteLn(', landing zone ', g.Lz);
end;

procedure DescribeType(Drive: Char);
var t: Integer;
begin
  t := DriveType(Drive);
  Write('  Drive ', Drive, ': type ', t, '  ');
  case t of
    0: WriteLn('(not installed)');
    1: WriteLn('(user defined - this table)');
    2: WriteLn('(automatic detection)');
    3: if Drive = 'D' then WriteLn('(automatic detection)') else WriteLn('(invalid)');
  else
    WriteLn('(standard table entry)');
  end;
end;

procedure ShowCurrent;
var g: TGeom;
begin
  WriteLn('Current settings:');
  DescribeType('C');
  DescribeType('D');
  ReadTable(g);
  Write('  Type 1 table (CMOS 72h-7Ch): ');
  if TableValid then
  begin
    WriteLn('valid');
    Write('    ');
    PrintGeom(g);
  end
  else
    WriteLn('not set or checksum wrong');
  if (CmosRead($0E) and $C0) <> 0 then
    WriteLn('  Note: CMOS is flagged invalid (battery/checksum); BIOS will load defaults.');
  if not MainValid then
    WriteLn('  Note: main CMOS checksum (2Eh/2Fh) does not match.');
end;

{ ------------------------------------------------------------ write table }

function WriteTable(const g: TGeom): Boolean;
var b: array[0..9] of Byte; i: Integer; s: Word; ctl: Byte;
begin
  if g.Heads > 8 then ctl := $08 else ctl := $00;
  b[0] := Lo(g.Cyl);  b[1] := Hi(g.Cyl);
  b[2] := g.Heads;
  b[3] := Lo(g.Wpc);  b[4] := Hi(g.Wpc);
  b[5] := 0;
  b[6] := ctl;
  b[7] := Lo(g.Lz);   b[8] := Hi(g.Lz);
  b[9] := g.Spt;
  s := 0;
  for i := 0 to 9 do
  begin
    CmosWrite(RegTable + i, b[i]);
    s := s + b[i];
  end;
  CmosWrite(RegTableSum, Lo(s));
  { read back }
  WriteTable := TableValid;
  for i := 0 to 9 do
    if CmosRead(RegTable + i) <> b[i] then WriteTable := False;
end;

function SetDriveType(Drive: Char): Boolean;
var t: Byte; s: Word;
begin
  t := CmosRead(RegTypes);
  if Drive = 'C' then t := (t and $0F) or $10
  else t := (t and $F0) or $01;
  CmosWrite(RegTypes, t);
  s := MainSum;
  CmosWrite(RegCsumHi, Hi(s));
  CmosWrite(RegCsumLo, Lo(s));
  SetDriveType := (CmosRead(RegTypes) = t) and MainValid;
end;

{ ------------------------------------------------------------ IDE detect }

{$ifndef SIMCMOS}
function InB(P: Word): Byte; assembler;
asm
  mov dx, P
  in al, dx
end;

procedure OutB(P: Word; V: Byte); assembler;
asm
  mov dx, P
  mov al, V
  out dx, al
end;

function InW(P: Word): Word; assembler;
asm
  mov dx, P
  in ax, dx
end;

function Ticks: Word;
begin
  Ticks := MemW[$40:$6C];
end;

{ Wait until (status and Mask) = Want, max ~2 s. Returns last status or $FFFF on timeout. }
function WaitStatus(Mask, Want: Byte): Word;
var t0: Word; st: Byte;
begin
  t0 := Ticks;
  repeat
    st := InB($1F7);
    if (st and Mask) = Want then
    begin
      WaitStatus := st;
      Exit;
    end;
  until Word(Ticks - t0) > 36;
  WaitStatus := $FFFF;
end;

function DetectIde(Slave: Boolean; var g: TGeom): Boolean;
var id: array[0..255] of Word; i: Integer; st: Word; sel: Byte;
    cyl, heads, spt: Word;
begin
  DetectIde := False;
  if Slave then sel := $B0 else sel := $A0;
  Write('Detecting primary ');
  if Slave then Write('slave') else Write('master');
  WriteLn(' drive...');
  OutB($1F6, sel);
  st := WaitStatus($80, $00);
  if (st = $FFFF) or (st = $FF) or (st = $7F) then
  begin
    WriteLn('  No drive responds.');
    Exit;
  end;
  if (InB($1F4) = $14) and (InB($1F5) = $EB) then
  begin
    WriteLn('  This is an ATAPI device (CD-ROM etc.), not a hard disk.');
    Exit;
  end;
  OutB($1F7, $EC);                          { IDENTIFY DEVICE }
  st := WaitStatus($89, $08);               { BSY=0, DRQ=1 }
  if st = $FFFF then
  begin
    if (InB($1F4) = $14) and (InB($1F5) = $EB) then
      WriteLn('  This is an ATAPI device (CD-ROM etc.), not a hard disk.')
    else
      WriteLn('  Drive did not answer IDENTIFY.');
    Exit;
  end;
  for i := 0 to 255 do
    id[i] := InW($1F0);
  cyl := id[1]; heads := id[3]; spt := id[6];
  Write('  Model: ');
  for i := 27 to 46 do
    Write(Chr(Hi(id[i])), Chr(Lo(id[i])));
  WriteLn;
  WriteLn('  Drive reports ', cyl, ' cylinders, ', heads, ' heads, ', spt, ' sectors/track');
  if (heads = 0) or (heads > 16) or (spt = 0) or (spt > 63) or (cyl = 0) then
  begin
    WriteLn('  Reported geometry is not usable.');
    Exit;
  end;
  if cyl > 1024 then
  begin
    WriteLn('  More than 1024 cylinders: using 1024 (BIOS limit, about 504 MB).');
    cyl := 1024;
  end;
  g.Cyl := cyl; g.Heads := heads; g.Spt := spt;
  g.Wpc := $FFFF; g.Lz := cyl;
  DetectIde := True;
end;
{$endif}

{ ------------------------------------------------------------ UI helpers }

function IsNcrBios: Boolean;
{$ifdef SIMCMOS}
begin
  IsNcrBios := True;
end;
{$else}
begin
  IsNcrBios := (Mem[$F000:$FFEA] = Ord('N')) and (Mem[$F000:$FFEB] = Ord('C'))
           and (Mem[$F000:$FFEC] = Ord('R'));
end;
{$endif}

function Confirm(const Q: string): Boolean;
var s: string;
begin
  if AssumeYes then
  begin
    Confirm := True;
    Exit;
  end;
  Write(Q, ' (Y/N)? ');
  ReadLn(s);
  Confirm := (s <> '') and (UpCase(s[1]) = 'Y');
end;

function AskNum(const Prompt: string; Def, Min, Max: LongInt; var V: Word): Boolean;
var s: string; n: LongInt; code: Integer;
begin
  AskNum := False;
  repeat
    Write(Prompt, ' [', Def, ']: ');
    ReadLn(s);
    if s = '' then n := Def
    else
    begin
      Val(s, n, code);
      if code <> 0 then n := -1;
    end;
    if (n >= Min) and (n <= Max) then
    begin
      V := n;
      AskNum := True;
      Exit;
    end;
    WriteLn('  Enter a number from ', Min, ' to ', Max, '.');
  until False;
end;

function ValidGeom(const g: TGeom): Boolean;
begin
  ValidGeom := (g.Cyl >= 1) and (g.Cyl <= 1024) and (g.Heads >= 1) and (g.Heads <= 16)
           and (g.Spt >= 1) and (g.Spt <= 63);
end;

procedure Usage;
begin
  WriteLn('Usage:');
  WriteLn('  USERHDD                      show settings, then enter a geometry');
  WriteLn('  USERHDD cyl heads spt [precomp [landing]] [options]');
  WriteLn('  USERHDD /DETECT [/SLAVE] [options]   read geometry from an IDE drive');
  WriteLn('  USERHDD /SHOW                show current settings only');
  WriteLn('Options:');
  WriteLn('  /C or /D   also set drive C: or D: to type 1 (no need to run Setup)');
  WriteLn('  /Y         do not ask for confirmation');
  WriteLn('Limits: cylinders 1-1024, heads 1-16, sectors 1-63. precomp 65535 = none.');
  WriteLn('For IDE drives over 504 MB use 1024 16 63.');
end;

{ ------------------------------------------------------------ main }

var
  g, cur: TGeom;
  nums: array[1..5] of LongInt;
  nNums, i, code: Integer;
  a: string;
  doShow, doDetect, haveGeom: Boolean;

begin
  WriteLn('USERHDD ', Version, ' - user defined hard disk for NCR 3230 BIOS 517-0000672');
  {$ifdef SIMCMOS}
  SimLoad;
  WriteLn('(simulation: using CMOS.BIN)');
  {$endif}
  ForceRun := False; AssumeYes := False; WantSlave := False; SetDrive := ' ';
  doShow := False; doDetect := False; nNums := 0;
  for i := 1 to ParamCount do
  begin
    a := ParamStr(i);
    if (a[1] = '/') or (a[1] = '-') then
    begin
      a := Copy(a, 2, 255);
      if a = '' then a := '?';
      case UpCase(a[1]) of
        'C': SetDrive := 'C';
        'D': if (Length(a) > 1) and (UpCase(a[2]) = 'E') then doDetect := True
             else SetDrive := 'D';
        'S': if (Length(a) > 1) and (UpCase(a[2]) = 'H') then doShow := True
             else WantSlave := True;
        'Y': AssumeYes := True;
        'F': ForceRun := True;
      else
        begin
          Usage;
          Halt(0);
        end;
      end;
    end
    else
    begin
      if nNums = 5 then
      begin
        Usage;
        Halt(1);
      end;
      Inc(nNums);
      Val(a, nums[nNums], code);
      if code <> 0 then
      begin
        WriteLn('Not a number: ', a);
        Halt(1);
      end;
    end;
  end;

  if not IsNcrBios and not ForceRun then
  begin
    WriteLn('This does not look like the NCR BIOS (no "NCR" at F000:FFEA).');
    WriteLn('Writing CMOS 72h-7Ch on another machine could damage its settings.');
    WriteLn('Use /F to run anyway.');
    Halt(2);
  end;

  ShowCurrent;
  WriteLn;
  if doShow then Halt(0);

  ReadTable(cur);
  if not TableValid or not ValidGeom(cur) then
  begin
    cur.Cyl := 1024; cur.Heads := 16; cur.Spt := 63; cur.Wpc := $FFFF; cur.Lz := 1024;
  end;
  g := cur;
  haveGeom := False;

  if doDetect then
  begin
    {$ifdef SIMCMOS}
    WriteLn('/DETECT is not available in simulation.');
    Halt(1);
    {$else}
    if not DetectIde(WantSlave, g) then Halt(1);
    haveGeom := True;
    {$endif}
  end
  else if nNums > 0 then
  begin
    if nNums < 3 then
    begin
      Usage;
      Halt(1);
    end;
    if (nums[1] < 1) or (nums[1] > 1024) or (nums[2] < 1) or (nums[2] > 16)
       or (nums[3] < 1) or (nums[3] > 63) then
    begin
      WriteLn('Out of range. Cylinders 1-1024, heads 1-16, sectors 1-63.');
      Halt(1);
    end;
    g.Cyl := nums[1]; g.Heads := nums[2]; g.Spt := nums[3];
    g.Wpc := $FFFF; g.Lz := g.Cyl;
    if nNums >= 4 then g.Wpc := nums[4];
    if nNums >= 5 then g.Lz := nums[5];
    haveGeom := True;
  end
  else
  begin
    WriteLn('Enter the new geometry (Enter keeps the value in brackets).');
    AskNum('Cylinders (1-1024)', cur.Cyl, 1, 1024, g.Cyl);
    AskNum('Heads (1-16)', cur.Heads, 1, 16, g.Heads);
    AskNum('Sectors per track (1-63)', cur.Spt, 1, 63, g.Spt);
    AskNum('Write precomp cylinder (65535 = none)', cur.Wpc, 0, 65535, g.Wpc);
    AskNum('Landing zone cylinder', g.Cyl, 0, 65535, g.Lz);
    haveGeom := True;
  end;

  if not haveGeom then Halt(0);
  Write('New type 1 geometry: ');
  PrintGeom(g);
  if SetDrive <> ' ' then
    WriteLn('Drive ', SetDrive, ': will be set to type 1.');
  if not Confirm('Write to CMOS') then
  begin
    WriteLn('Nothing written.');
    Halt(0);
  end;

  if not WriteTable(g) then
  begin
    WriteLn('ERROR: CMOS read-back does not match. Is the CMOS battery OK?');
    Halt(4);
  end;
  WriteLn('Type 1 table written and verified.');
  if SetDrive <> ' ' then
  begin
    if not SetDriveType(SetDrive) then
    begin
      WriteLn('ERROR: could not set the drive type.');
      Halt(4);
    end;
    WriteLn('Drive ', SetDrive, ': set to type 1, CMOS checksum updated.');
  end
  else
    WriteLn('Now run Setup (F1 at boot) and set the fixed disk to type 1.');
  WriteLn('Restart the computer for the change to take effect.');
end.
