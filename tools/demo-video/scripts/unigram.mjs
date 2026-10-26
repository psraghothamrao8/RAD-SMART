// The Telegram app on the recording machine (Unigram, from the Microsoft Store), for the
// video's Telegram scene: its window is set to a phone's shape beside the screen's edge,
// and its frames are captured with Windows Graphics Capture (ffmpeg's gfxcapture filter,
// ffmpeg 8 or later) while the recorder asks for them, each stamped with the recorder's
// clock. Only the bot's chat is open in a window this narrow: the chat list is not shown.
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PHONE = { w: 430, h: 720 };   // the window, in screen pixels
const TITLE_BAR = 32;               // the window's own title bar, cropped off

const WIN32 = `Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class U {
  public delegate bool P(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(P f, IntPtr l);
  [DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  [StructLayout(LayoutKind.Sequential)] public struct WP { public int length, flags, showCmd, x1, y1, x2, y2, l, t, r, b; }
  [DllImport("user32.dll")] public static extern bool GetWindowPlacement(IntPtr h, ref WP p);
  [DllImport("user32.dll")] public static extern bool SetWindowPlacement(IntPtr h, ref WP p);
  /// Restored (not maximized or minimized) without taking the focus.
  public static void Normal(IntPtr h) { var p = new WP(); p.length = Marshal.SizeOf(p); GetWindowPlacement(h, ref p); p.flags = 0; p.showCmd = 4; SetWindowPlacement(h, ref p); }
  public static IntPtr Find() {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => { var t = new StringBuilder(64); GetWindowText(h, t, 64); var c = new StringBuilder(64); GetClassName(h, c, 64);
      if (t.ToString() == "Unigram" && c.ToString() == "ApplicationFrameWindow") { found = h; return false; } return true; }, IntPtr.Zero);
    return found;
  }
}
"@
$h = [U]::Find(); if ($h -eq [IntPtr]::Zero) { throw "Unigram is not running" }
`;
const ps = (body) => execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", WIN32 + body], { encoding: "utf8" }).trim();

/** Phone-shaped at the right of the screen, behind other windows, without taking the focus.
 *  Returns how it was, for restore(). */
export function phoneShape() {
  return ps(`
Add-Type -AssemblyName System.Windows.Forms
$was = if ([U]::IsIconic($h)) { "minimized" } elseif ([U]::IsZoomed($h)) { "maximized" } else { "normal" }
[U]::Normal($h)
$area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
[void][U]::SetWindowPos($h, [IntPtr]1, $area.Right - ${PHONE.w} - 8, $area.Top, ${PHONE.w}, ${PHONE.h}, 0x0010)   # HWND_BOTTOM, SWP_NOACTIVATE
$was`);
}

/** Back as it was: maximized, and minimized again if it was. */
export function restore(was) {
  if (was === "normal") return;
  ps(`[void][U]::ShowWindow($h, 3); if ("${was}" -eq "minimized") { [void][U]::ShowWindow($h, 7) }`);
}

/** Opens a bot's t.me link in the app itself (tg://), which shows that chat: with its
 *  START button for the link's own start parameter, or just the chat with `chatOnly`. */
export function openLink(url, chatOnly = false) {
  const u = new URL(url);
  const start = !chatOnly && u.searchParams.get("start");
  const tg = `tg://resolve?domain=${u.pathname.slice(1)}${start ? `&start=${start}` : ""}`;
  execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", `Start-Process '${tg}'`]);
}

/** Presses the START button of the bot's chat that openLink() has shown (UI Automation):
 *  true once it is pressed, false if the chat shows none. */
export function pressStart() {
  return ps(`
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)))
$start = $buttons | Where-Object { $_.Current.Name.Trim() -eq "Start" } | Select-Object -First 1
if ($start) { $start.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); "pressed" } else { "none" }`) === "pressed";
}

/** A JPEG's width and height, from its frame header. */
function jpegSize(jpg) {
  for (let i = 2; jpg && i < jpg.length - 8; ) {
    const marker = jpg[i + 1], len = jpg.readUInt16BE(i + 2);
    if (marker >= 0xc0 && marker <= 0xc2) return { w: jpg.readUInt16BE(i + 7), h: jpg.readUInt16BE(i + 5) };
    i += 2 + len;
  }
  return null;
}

/** Captures the window into `dir` while on: frames arrive when the window changes. */
export function capture(dir, now) {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const ff = spawn("ffmpeg", ["-hide_banner", "-loglevel", "error", "-filter_complex",
    `gfxcapture=window_title=^Unigram$:window_class=ApplicationFrameWindow:max_framerate=15:capture_cursor=0:crop_top=${TITLE_BAR},hwdownload,format=bgra`,
    // one encoder thread: with more, each frame waits for the next ones, which may never come
    "-f", "image2pipe", "-c:v", "mjpeg", "-threads", "1", "-q:v", "3", "-"], { stdio: ["ignore", "pipe", "inherit"] });
  const SOI = Buffer.from([0xff, 0xd8]), EOI = Buffer.from([0xff, 0xd9]);
  const frames = [];
  let buf = Buffer.alloc(0), last = null, on = false, saved = 0, later = null;
  const write = (jpg) => {
    const file = `u_${String(frames.length).padStart(5, "0")}.jpg`;
    writeFileSync(join(dir, file), jpg);
    frames.push({ file, t: (saved = now()) });
  };
  // at most 30 frames a second (the app may redraw far more often), the last one always kept
  const save = (jpg) => {
    clearTimeout(later);
    const wait = saved + 1000 / 30 - now();
    if (wait <= 0) write(jpg);
    else later = setTimeout(() => on && write(jpg), wait);
  };
  ff.stdout.on("data", (d) => {
    buf = Buffer.concat([buf, d]);
    for (;;) {
      const a = buf.indexOf(SOI);
      const b = a < 0 ? -1 : buf.indexOf(EOI, a + 2);
      if (b < 0) {
        buf = a < 0 ? Buffer.alloc(0) : buf.subarray(a);
        break;
      }
      last = Buffer.from(buf.subarray(a, b + 2));
      buf = buf.subarray(b + 2);
      if (on) save(last);
    }
  });
  return {
    frames,
    size: () => jpegSize(last),
    start() {
      on = true;
      if (last) save(last);   // what the window shows now, until it changes
    },
    stop() {
      on = false;
    },
    close: () => ff.kill(),
  };
}
