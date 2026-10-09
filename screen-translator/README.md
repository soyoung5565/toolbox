# Screen Translator · 屏幕实时翻译

> Windows 桌面悬浮翻译工具：框选屏幕任意区域 → OCR + 翻译 → 覆盖显示原文/译文。
> *A floating screen-translation overlay for Windows: capture any region, OCR + translate, display inline — like the AI translate feature in mobile browsers, but for your desktop.*

## 功能

- 🖱 **区域截图翻译**：框选屏幕区域，实时 OCR + 翻译（MIMO v2.5 多模态模型）
- 🪟 **悬浮覆盖**：翻译结果直接覆盖在原内容上，不打断阅读
- ⚙️ **可调参数**：刷新间隔、字号、透明度等（界面控制）
- ⌨️ 快捷键操作

## 技术栈

- Python + PyQt5（悬浮窗/绘制/交互）
- mss（屏幕捕获）+ Pillow（图像处理）
- MIMO v2.5 多模态 API（OCR + 翻译一体）

## 运行

```bash
pip install PyQt5 mss Pillow requests
export MIMO_API_KEY=你的key   # 或修改脚本内配置
python screen_translator.py
```

> 将脚本内的 `YOUR_API_KEY` 替换为你的 MIMO API Key（或通过环境变量注入）。

## 备注

适用于看外语视频、外语文档、生肉直播等场景的即时翻译需求。
