# VideoDock 🎬

一款基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的开源视频下载器 GUI —— 
为不想敲命令行的你而生。下载安装、开箱即用，零环境配置。

## ✨ 特性

- **双模式**：简易模式点几下就能下；高级模式暴露 yt-dlp 全部参数，
  改动实时生成命令预览，可一键复制到终端执行
- **批量下载**：链接框每行一个，回车整批入队；支持拖拽粘贴
- **任务队列**：并发数可调；单任务 暂停/恢复/取消/重新下载；
  一键重下全部失败任务
- **断点续传**：暂停与失败的任务从断点继续，不浪费已下载部分
- **下载历史**：本地持久化，支持筛选/搜索/导出 CSV/右键重试
- **防限流助手**：代理池轮换（每 N 个任务切换出口）+ 任务间隔
- **Cookie 支持**：自动检测本机浏览器（Chrome/Edge/Firefox 等）
  的登录凭据，通过会员/年龄限制与机器人验证
- **完成反馈**：桌面右下角弹窗 + 提示音（可开关）
- **多语言**：中文 / English / Français / Español / Русский / 日本語 / 한국어
- **安装器**：内置 yt-dlp 与 ffmpeg，双击安装自动完成全部配置，
  支持开始菜单/桌面快捷方式与系统卸载

## 📦 下载与安装

1. 到 [Releases](../../releases) 页面下载 `VDSetup.exe`
2. 双击运行（首次运行如遇 SmartScreen 提示，点
   「更多信息 → 仍要运行」，未签名的免费软件正常现象）
3. 按向导选择安装目录（默认 `D:\Program Files\VideoDock`），
   自动检测浏览器 Cookie，完成

安装器已内置 yt-dlp.exe 与 ffmpeg.exe，**无需 Python、无需任何运行库**。

> 便携偏好者：安装向导默认即为便携模式，程序目录整个拷走即用。

## 🚀 快速上手

1. 把视频链接粘贴到顶部输入框（每行一个）
2. 回车（或点「开始下载」）
3. 在「下载任务」页看进度，完成后在「下载历史」页找到文件

遇到平台提示 *Sign in to confirm you're not a bot*？
到「设置」页选择你登录过 YouTube 的浏览器并检测通过即可。

## 🧩 支持的网站

理论上支持 yt-dlp 全部站点（上千个），包括 YouTube、Bilibili、
Twitter/X、Instagram、TikTok、Twitch、SoundCloud 等。
完整列表见 [yt-dlp 支持列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)。

## ⚠️ 免责声明

- 本工具仅供个人学习、备份与研究使用。请遵守当地法律法规、
  平台用户协议与内容版权声明；下载受版权保护内容的责任由
  使用者自行承担
- 请勿用于任何商业用途或批量牟利行为
- 网站改版可能导致临时失效，通常更新 yt-dlp 后即恢复

## 🙏 致谢

VideoDock 只是图形外壳，真正的下载与转码能力来自：

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) —— 下载内核
- [FFmpeg](https://ffmpeg.org) —— 音视频处理内核
- [PySide6 (Qt)](https://www.qt.io/) —— 界面框架

向以上项目的开发者与贡献者致敬，欢迎去给它们点 Star。

## 📄 许可证

本项目代码以 [MIT License](LICENSE) 发布。分发包中的
yt-dlp 与 ffmpeg 分别遵循其自身的开源许可证（Unlicense /
GPL 或 LGPL），详情见各自项目主页。

## ❓ 常见问题

**下载速度/进度不显示？** 更新到最新 Release；若仍复现，
请附带任务卡片上的错误信息（悬停可看全文）提 Issue。

**杀毒软件报毒？** PyInstaller 打包的未签名程序常见误报，
可添加信任或自行从源码构建（见下）。

**如何更新内核？** 「设置」页 yt-dlp 一行点「下载最新版」，
下载后替换程序目录内的 yt-dlp.exe。
