"""测试鼠标录制 - 请直接双击运行"""
import time
import sys

print("测试1: mouse 库")
try:
    import mouse
    events = []
    def on_event(e):
        events.append(str(e))
    mouse.hook(on_event)
    print("  请点击鼠标左键3次（5秒内）...")
    time.sleep(5)
    mouse.unhook_all()
    print(f"  结果: 捕获 {len(events)} 个事件")
    for e in events[:5]:
        print(f"    {e}")
except Exception as ex:
    print(f"  失败: {ex}")

print()
print("测试2: pynput 库")
try:
    from pynput import mouse as pm
    events2 = []
    def on_click(x, y, button, pressed):
        action = "按下" if pressed else "释放"
        events2.append(f"{action} {button} ({x},{y})")
    listener = pm.Listener(on_click=on_click)
    listener.start()
    print("  请点击鼠标左键3次（5秒内）...")
    time.sleep(5)
    listener.stop()
    print(f"  结果: 捕获 {len(events2)} 个事件")
    for e in events2[:5]:
        print(f"    {e}")
except Exception as ex:
    print(f"  失败: {ex}")

print()
print("测试3: ctypes GetCursorPos")
try:
    import ctypes, ctypes.wintypes
    user32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    positions = []
    print("  请移动鼠标（5秒内）...")
    for i in range(50):
        user32.GetCursorPos(ctypes.byref(pt))
        positions.append((pt.x, pt.y))
        time.sleep(0.1)
    unique = set(positions)
    print(f"  结果: {len(unique)} 个不同位置")
    for p in list(unique)[:5]:
        print(f"    ({p[0]},{p[1]})")
except Exception as ex:
    print(f"  失败: {ex}")

input("\n按回车退出...")
