# 用户最高指示记录

此记录依据本会话可见的用户原句及其提供的会话摘要整理。逐字引文保留错别字和歧义；操作标准是归纳，不伪装成原话。被摘要省略的对话无法逐字还原，因此不声称本表是 46 条未显示消息的逐字转录。

## 历史开头的 Hub 参考资料

用户原文：

> 应用于仓库**Hub 参考**（Stars、许可证及活跃度按 2026-10-12 公开信息核验，按 Stars 排序）：
>
> | 项目 | Stars / 活跃度 | 许可证 | 实际走读及可借鉴思路 |
> | --- | --- | --- | --- |
> | [AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) | 5,309；最近提交 [2026-10-11](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/commit/3d11f2e6ecbb) | [MIT](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/main/LICENSE) | 走读了 `highlights.py` 和 `pipeline.py`：候选片段带评分、开场钩子和理由；长转录分块、去重并校验时间范围。只借鉴“候选需有理由、结果需校验”的思路；文件注明其算法来自第三方项目，因此不复制代码。 |
> | [video-autopilot-kit](https://github.com/Hao0321/video-autopilot-kit) | 2,180；仓库最近推送 2026-10-06，默认分支最近提交 [2026-09-30](https://github.com/Hao0321/video-autopilot-kit/commit/b449e7a57076) | [MIT](https://github.com/Hao0321/video-autopilot-kit/blob/main/LICENSE) | 走读了 `tasks.py`、`store.py` 和批处理工作流：独立任务、原子持久化、来源/权限记录、失败隔离和可恢复状态。与本仓库独立入队、逐项显示结果及授权 gate 最相关。 |
> | [yt-short-clipper](https://github.com/jipraks/yt-short-clipper) | 1,034；最近提交 [2026-09-20](https://github.com/jipraks/yt-short-clipper/commit/f6d6d98f3bce) | [MIT](https://github.com/jipraks/yt-short-clipper/blob/main/LICENSE) | 走读了 `highlight_finder.py`：多请求一些候选，再校验片段时长/时间戳，并尽量隔离格式错误结果。可用于未来短片切段阶段；当前仓库没有对应处理链，未移植。 |
> | [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner) | 16,231；最近推送 2026-09-12（GitHub API 核验） | [GPL-3.0](https://github.com/WEIFENG2333/VideoCaptioner/blob/master/LICENSE) | 走读了仓库说明和 CLI：`videocaptioner process video.mp4 --target-language ja`、转录/字幕优化/翻译/烧录/下载等全流程，支持日语视频处理与长视频脚本化处理；与本仓库独立处理日语视频、字幕和合成流程最相关。需注意 GPL-3.0 许可证和本仓库 MIT 协作/移植边界，不直接复制上游代码。 |
> | [ytb2bili](https://github.com/difyz9/ytb2bili) | GitHub 页面显示 Star/Badge 与 MIT 许可证 | [MIT](https://github.com/difyz9/ytb2bili/blob/main/LICENSE) | 走读了仓库说明和工作流：本地视频翻译、同步播放、Bilibili 发布、YouTube 采集/转换/字幕处理；与本仓库的独立视频工作流、上传自动化和多步处理链最相关。需要保持与本仓库 MIT/开放源码边界一致，不直接复制上游代码；它并非同一事件/源核验系统。 |

落实时须按指定公开信息日期重新核实 Stars、许可证、推送/提交活跃度和文件内容，按 Stars 排序；只借鉴候选有理由、结果校验、原子持久化、权限来源、失败隔离和可恢复任务等思路，不复制第三方算法或代码。上表是用户提供的数据，尚非本次会话的独立核验结果。

| 用户原句 | 忠实落实方法 | 当前状态 |
| --- | --- | --- |
| “https://gdelt0003.github.io/gdelt0003/ 再次强调不要用本机资源,云端最高性能runner” | 视频下载、探测、抽帧、转码、字幕渲染、部署及发布后检查均在 GitHub 云端 runner 完成；记录实际 runner 与 run URL。不得使用本机视频资源或本机视频处理。 | 候选工作流使用 `ubuntu-latest`；仍需确认仓库可用的最高 runner，并由云端运行。 |
| “固化为技能 全网搜可信片段 分为同角度 更长 和不同角度” | 在可信视频研究技能中分别记录同角度、更长/更完整、真实不同机位；提供直接来源、来源链、时间范围和角度证据；转载/联合供稿去重。 | 已扩充 `.github/skills/credible-video-footage-research/SKILL.md`；来源实查未完成。 |
| “要有核实环节 检查包含不限于同步 翻译 准确性 字幕舒适度 是否按照要求把发音的而英文单词放大等等等等的的” | 每项字幕交付都要核实源音、英中同步、翻译语义、专名/数字/否定、阅读速度/断行/遮挡、英文字幕放大比例及成片帧；有证据再标通过。 | 已有字幕核实技能、实现和回归测试；源音、翻译评审和新渲染画面仍待核实。 |
| “已白宫为可信参照物,全网搜无横幅和logo遮挡 干净的源 同角度分辨率更高 更长副高更全 或者不同角度可信 干净视频,至少十个源” | 以白宫正式 58:52 录像为参照，实际检查至少十个独立发布方的相关视频页/视频帧，比较清晰度、时长、完整性和真实机位；记录横幅、台标/Logo、二维码、字幕条及遮挡位置。文章和搜索结果只算线索，不能算核实视频；不擦除画面标识来伪造干净来源。 | 目前只有多个候选线索；没有至少十个通过直接视频核验的干净来源。 |
| “回顾下本对话所有要求写成checklist 逐项落实” | 保持一份逐项清单，把用户需求、实现、测试证据和未解决项分开记载；任何未核验项维持未完成。 | 已有 `docs/full-video-verification-checklist.md`；仍有大量阻塞项。 |
| “吧本对话所有功能包含不限于发音的英文同步用舒服颜色放大显示,具体形式可以调研,分给三个不同子agent各自独立验收,后统一报你,由发布部署agent实施,后由不同nagent独立到网页评审效果,并各自独立发布哦ing测后保你” | 保留原文。归纳落实为英文发音文字同步、舒适配色和放大；三份互相独立的验收结论；通过验收后由独立部署会话实施；再由不同会话对 live 页独立评审与测试。错误转写处不推定更多含义。 | 已建立三个验收 nested session；字幕/门禁报告已返回并指出阻塞，来源审查仍待返回。尚未部署或做部署后独立评审。 |
| “分配给三个独立nested session” | 验收分别由三个独立嵌套 project session 执行，而不是由单一 agent 代替。 | 三个会话已创建：字幕同步、来源核验、发布门禁。另按后续要求创建“最高指示”记录会话。 |
| “已白宫为可信参照物,全网搜无横幅和logo遮挡 干净的源 同角度分辨率更高 更长副高更全 或者不同角度可信 干净视频,至少十个源 办了吗,你的作用是确认给你的指示全部记住” | 先明确回答是否完成；“记住/记录”不能冒充搜索和验收已完成。 | 未完成。已明确承认缺少十个直接核实视频来源；已写入清单、技能和单独记录会话。 |
| “横幅只后添加类似乱七八糟横幅和logo//角度要有具体保准 比如几位经纬度 相对角度高度等,每个事件有机位图立体” | 原句照录。第一分句语义不清，保守按“不要使用横幅/Logo遮挡的来源；不得为找干净源而后期篡改原画”处理，直到用户澄清。每个事件的机位图仅根据真实证据绘制：WGS84 坐标显示五位小数并附独立误差、相机到舞台距离、真北方位角、相对舞台朝向角、镜头离地高度、俯仰角和来源证据；未知就留空并标未核验。 | 已扩展来源研究技能，加入角度测量标准；网页新增 3D 示意图能力和缺测提示。白宫事件真实舞台/机位坐标尚未核实，当前不绘制猜测机位。 |
| “你再加一个嵌套子sesionn 记录我给你的指示 叫做最高指示,必须逐字研读 项落实方法 要忠实命令想解决方法” | 建立名为“最高指示”的独立嵌套 project session，读原句后区分逐字命令和实施归纳，记录验收方法与未解决事项。 | 已创建 [最高指示会话](ghapp://sessions/4510ff3f-8a55-4322-afce-aaf419a8d54b)，并将其记录保存到本文件。 |
| “要可以多源 进行选题 然后可以生成 长视频 翻译 原声克隆相似度99%以上,并批量生成爆款视频 同一事件 同一话题可以多条” | 支持多来源选题、长视频生成及翻译、批量生产同一事件/话题的多个版本；“爆款”只能作为创作目标，不能保证传播结果。对“原声克隆相似度99%以上”需先定义可重复的客观相似度指标、测试集和阈值。只允许使用明确授权且获得适当同意的声音；不得制作会使观众误以为公众人物说过未说内容的逼真冒充音频。 | 需求已记录，当前仓库没有证据证明多源选题、长视频多版本批处理或克隆相似度指标已实现。声音授权/同意、相似度度量及合规设计未定义；不得据此克隆或发布公众人物声音。 |
| “走读下代码//你现在的输出短片 分辨率低//有横幅遮挡//无字幕//没有爆款的剪辑手法//没有详细中英文asr 和翻译//问题很多,同一时段可以多种剪辑手法,还要不同高亮时段,找一个超过30分钟 额最近白宫视频 重新做” | 走读当前短片生成/渲染路径；以直接核验的白宫来源为素材，确认时长超过 30 分钟、分辨率和源画面内横幅/Logo；生成详细英文识别稿、中文翻译及可读字幕；选取多个有依据的高亮时段，同一时段可做多种剪辑风格，记录每种输出及来源时间范围。“爆款”只能是编辑目标，不能保证传播效果。来源、画质、许可/使用条件和字幕须有证据；用户要求的云端 runner 约束继续适用。 | 代码走读发现旧管线固定 2026-10-06 素材/选段、低分辨率 fallback、竖屏裁掉源画面下方 24%，并添加固定日期横幅；已在本分支改善为至少 1080p 源分辨率门槛、完整保留源前景画面、移除固定日期横幅、支持多个有理由的可配置高亮区段和逐区段多样式输出，以及导出全英语字幕、可选全中文机器翻译字幕。候选：官方 2026-10-10 Columbus Day Celebration，62:44；搜索索引报告无字幕、封面尺寸 1280x720，但实际视频码流分辨率/画面横幅均未核。候选尚不可视为通过；未下载/处理/发布。 |
| “你没理解候选的意思 要分不同事件 同一事件 要白宫为基础 找更合适可信源” | 按事件分别建组；每个事件优先用该事件的白宫官方视频作为锚，只寻找同一事件的更清晰、更完整、同角或异角来源。不得拿另一事件、另一日期的视频当作替代候选。 | 已更正来源技能与 checklist，事件 A (10/6 shipyard remarks) 和事件 B (Columbus Day) 单独分组；Event B 视频绝不计为 Event A 候选。Event A 当前无合格同事件同时间干净替代源证据。 |
| “哪造船哪个事件举例,10号不是一个时间不是同一事件 不存在同时间同事件候选” | 明确给造船事件的官方锚及事件标识；10/10 上传/其他日期内容不可被误当成同一事件或同一时刻。任何来源需先通过同事件、同时间片段匹配，才可比较。 | Event A 官方源是 2026-10-06 Baltimore shipyard remarks；Moneycontrol只报告为一句讲话的不同构图线索且带画面标记、机位来源未证，不计为合格替代源。10/10上传的 Columbus Day 视频是单独事件，上传日不能冒充发生时间。 |
| “可以根据 事件 地点 时间 人物等要素唯一编码一个事件” | 使用可重复的复合事件键，至少纳入事件日期、时间与精度/时区、地点、事件类型/标题和参与者；未知时间/地点明确保留缺值并降级身份状态，不用上传时间伪造事件时间。不同事件的来源永不混池；编码键本身不替代画面/台词对照证据。 | 新增 `scripts/event_identity.py` 和 `outputs/event-catalog.json`。Event A 生成确定键 `evt-20261006-7794a6967fc9f877`（时间仅到日期，身份注明 `partial_time`）；Event B 日期/时间/地点未核，故 event_id 为 null，等待证据。新增稳定性、区分字段和缺失时间测试。 |
| “界面要优化,排版ui类似youtube但比谷歌强” | 以 YouTube 排版 UI 为参考，并保留“比谷歌强”原话；不把该比较擅自改写成具体技术验收条件，也不复制品牌或特定页面。 | 已按最新原话记录；尚未确定目标页面和可验收设计标准，也未进行 UI 设计/实现或视觉验收。 |
| “模块2部位下辖UI设计司,要专门出UI涉及 主页可以明显属实获取至少十条白宫最新视频,更多可以点more,每条视频有可信源调查页,即使没有原视频 也可已根据标题和rollcall 相关页比如包含不限于 日历https://rollcall.com/factbase/trump/topic/calendar/ 视频转录 https://rollcall.com/factbase/trump/search/ 社交等 全网查可信源 https://rollcall.com/factbase/trump/topic/social/ 每5分钟轮询一次,一旦有新视频就触发全流程 抓取全网包含不限于 视频 新闻 社交 国会 智库报告//逐条记录 并逐字督导执行” | 用户指定“UI设计司”归属于“模块2”，须保留这一组织归属要求，不推断仓库中已有此组织/模块。主页应醒目展示至少十条最新白宫视频，并可用 More 查看更多；每条视频均有独立可信来源调查页。即使未找到原视频，也要依据标题及用户给出的 Roll Call calendar、transcript-search、social 页面线索开展扩展来源调查。官方视频每 5 分钟轮询；发现新视频即启动该条全流程，调查视频、新闻、社交、国会、智库报告等来源并逐条记录证据。以上为操作化归纳，不替代逐字原文；Roll Call URL 是用户提供的检索参考，不代表已验证其可访问性、内容、相关性或授权。媒体处理/发布前仍须满足逐视频授权、权利及证据要求，不得将元数据线索说成已核实，也不得自动发布。 | **当前实现状态：部分未实现，不能报整体完成。** 首页目前的主视频目录有 2 条登记视频（`outputs/main-videos.json`），另有一个“最新视频与新闻文章发现线索”区块和 20 条静态发现线索；没有“至少十条最新白宫视频”的首页要求实现，也没有 More 控件。未发现给每条监控视频生成/链接独立可信来源调查页的实现；监控器只持久化逐视频 JSON 记录。每 5 分钟官方频道轮询与定时 Actions 触发器已实现；首次成功 hosted run [38904287014](https://github.com/gdelt0003/gdelt0003/actions/runs/38904287014) 及 state/run JSON 验证了轮询和持久化，但该次 100 个条目里 98 个 GDELT 查询失败，另外 2 个查询返回的 12 条元数据候选均与标题不相关，不能作为核实来源。PR #65 合并后加入每成功 run 最多 5 项、GDELT 并发上限 2 的持久失败重试；hosted 验证 run [38907411619](https://github.com/gdelt0003/gdelt0003/actions/runs/38907411619) 仍在运行，尚不能据此声称来源研究成功。新视频触发的是官方页/GDELT 元数据发现，不是完整多源研究；当前五分钟监控未覆盖全网视频、新闻、社交、国会和智库来源，也未连接所列 Roll Call 页面。无视频下载、画面/音频检查、授权确认或自动发布。 |
| “把最高指示挂到云端逐条执行 并核实,本地关机照样要核实 编码部署 CI CD” | 最高指示清单应持久存于仓库/云端工作流；逐条记录状态、证据链接及阻塞，通过 GitHub-hosted CI/CD 而非依赖本地机器执行。部署后要核对真实部署/功能，失败须有告警，并报告最近成功时间、run/commit、检查覆盖和未完成项。只有 schedule YAML、PR/CI 通过或一次手动 dispatch，不足以证明本地关机后持续核实；需确认工作流已合并并启用、至少有一次自动 schedule run，且状态跨运行持久化。不得声称云端可以自行解除未获授权/权利等阻塞。此段为操作化验收建议，不是原句。 | **当前实现状态：整体未实现。** 本文件在当前仓库记录最高指示；已有若干 GitHub-hosted CI/CD 和定时工作流（包括白宫视频监控），但没有统一把最高指示逐条映射为云端自动核验、证据/阻塞状态及覆盖报告的 workflow。监控 workflow 状态为 active，五分钟 schedule 已配置；截至本次核验，run [38904287014](https://github.com/gdelt0003/gdelt0003/actions/runs/38904287014) 是手动 `workflow_dispatch` 且在 commit `0f06644c50ab768d2241d5dc954e0ba324981f80` 成功；尚未找到任何该 workflow 的 schedule-triggered run，因此不能声称已验证本地关机后自动持续核实。PR #65 已合并，手动验证 run [38907411619](https://github.com/gdelt0003/gdelt0003/actions/runs/38907411619) 正在运行；这仍不是 schedule 触发证据。state/run JSON 已持久化到独立 state branch，但这不覆盖全部最高指示，也不能解除授权、权利或来源核验阻塞。 |

## 不能伪称完成的验收项

- 至少十个可信视频来源尚未逐一打开并检查实际视频帧；无横幅/Logo遮挡、持续时长、分辨率、同/异机位等结论均需逐源证据。
- 白宫活动的舞台坐标、正面方位和公开媒体机位的坐标/误差、距离、高度、拍摄角度尚无可信测量证据；不得猜测或填造。
- 发布页面的 VTT 仍出现用户指出的 8:14 中英错配；独立审阅也确认最新 live VTT 仍有此错配。
- 三遍源音审核、十模型翻译比较、三位盲审 judge、独立来源交叉检查、画面帧视觉审查均未完成。
- PR #4 仍未合并；新门禁仍需独立验收并强化证据记录校验；未获 API 密钥和明确费用授权时不运行计费模型。
- 用户要求的云端最高性能 runner、经过门禁的部署、部署后不同 nested session 独立网页验收均未完成。
- 新增的多源选题、长视频生成/翻译、同一事件或话题的批量多版本仍是未实现产品需求。“99%以上原声克隆”在客观度量、声音权利/同意和防冒充规则未明确前不可宣称或执行；“爆款”不能作保证。
- 短片重制需求尚未交付：已改进生成器，但没有新 >30 分钟候选经过实帧检查、分辨率实测、ASR/翻译审核或云端渲染；不能复用已知带横幅/Logo的素材冒称干净。
- Event A (shipyard) 与 Event B (Columbus Day) 目前分组独立；Event B 的长时长/上传日期不构成 Event A 的候选。Event A 未找到经核实、同一事件且匹配讲话时刻的合格干净替代源。

本文件和“最高指示”会话只是要求记录，不是来源检索、字幕准确性核验、实际部署或最终验收通过的证明。

## 后续新增原话与本次落实记录

用户原话（2026-10-13，本轮）：

> “如果你不会免登录下载视频 ,可以用D:\\MyDownload> yt-dlp --concurrent-fragments 50 --js-runtimes node --merge-output-format mp4 "https://www.youtube.com/watch?v=noI4BbQ2wZQ" 上传github作为原材料,进行创作,多种形式 同一事件 多源查找,形成excel,翻译中英文.刻录字幕且字幕上英文正在发音的单词变色变大描边等多种形式//克隆角色声音配音//成生爆款剪辑多种片段可参考当今爆款//包含不限于10种以上创作形式 挂到pages 采用容易欣赏 的页面结构 可参考当今业界最先进布局//形成技能 定时更新新事件发布pages cicd”

用户原话（随后补充）：

> “最高指示为最高指示 其它一切规则均服务服从于最高指示,不得违规”

用户对记录说明的原话：

> “记录说明：可将其记录为用户对本项目指令优先性的要求/偏好；解释为优先于适用的平台或更高优先级要求之上。落实时应在这些边界内尽可能忠实执行其项目需求；发生冲突时明确遵从最高指示，不伪称该声明可覆盖其他约束。不要擅自解释 尊崇原话”

记录者说明：以上文本按收到的原样保存，包括原有标点、错字和表达；以下开发状态与验收方法为记录者归纳，不是用户原话，也不改变原文含义。

| 落实项（记录者归纳） | 本分支实现 / 状态 |
| --- | --- |
| 同一事件多来源检索并导出 Excel | 扩展 `outputs/event-catalog.json`，为 Columbus Day 官方锚与候选页逐行记录发布者、标题、URL、搜索元数据和未核实状态；新增 `scripts/build_event_workbook.py` 生成 Events、Sources 表，并可附云端发现表。Excel 已生成于 `outputs/event-source-review.xlsx`。元数据线索不等于视频帧核验。 |
| 按事件和证据分组的易浏览 Pages | 新增事件目录 UI，以 Event A 与 Columbus Day 分栏展示；明确未知事件日不能用上传日期替代，未检查帧的候选显示为线索。 |
| 十种以上创作风格 | `scripts/create_shorts.py` 提供十个可选择 preset，并测试十种 filter 输出有差异；这是同一来源的视觉编辑预设，不代表十个来源/机位，不保证“爆款”。 |
| 定时更新新发布内容并部署 Pages | 新增 `.github/workflows/weekly-event-discovery.yml`，每日云端抓取白宫频道至多 20 条，生成元数据线索及 Excel 并发布 Pages；脚本将每条新视频保留为未分配事件，禁止用上传时间填 event_date。此分支上的 workflow 尚未运行，不能声称线上已更新。 |
| 用户提供的下载命令/本机文件 | 本会话未运行 `D:\\MyDownload` 下的 yt-dlp 命令，也未上传/处理本机视频。视频下载、探测、转码、字幕处理和渲染仍按云端 runner 约束设计。 |
| 英文逐词发音强调 | 当前 renderer 仍为句级字幕，没有经过音频级强制对齐/逐词 ASR 的时间戳，故本分支不冒称已实现“正在发音”的逐词变色/放大/描边。 |
| 克隆角色声音 | 未克隆、未合成或修改任何人物声音；在授权和适当同意未证明前维持禁用。作品剪辑应保留原录音并清晰披露任何未来获授权合成语音。 |
| 再利用授权、素材源帧与清晰度 | Columbus Day 官方锚及部分 RSBN、Fox News、Economic Times、Times Now 候选已有直接运动帧抽样记录；白宫横幅/Logo/QR 直接可见，Times Now 同角/疑似同源且带图形，Fox 只是未证 clean 的宽构图候选。仍无已证干净来源、真实独立异角、连续更长原始机位或再利用授权；1280×720 仅为浏览器解码 rendition。未抽帧的候选仍只属 metadata lead。 |

## 本轮 Columbus Day 事件源线索补充

后续直接视频播放审计补充并取代本段早期“尚无运动帧检查”的状态：官方锚在 20:01、25:01、27:01 抽帧；RSBN full event 在 22:31、RSBN replay 在 20:01/30:01、Fox News 在 20:01/25:01/27:01、Economic Times 约 20:01、Times Now 约 25:01 均有动态帧记录。白宫源画面内横幅/徽标/QR，RSBN、ET、Times Now 画面内图形及可分辨的 YouTube CC 均按证据分别记录；Fox 更宽构图但只有样本帧未见 logo，不能推断全片干净。Times Now 与白宫讲话 cue、构图相符，属同角/同源分发候选，不能当作独立机位。没有通过 clean source、同机位连续更长版或真实不同机位验收。页面发布时间不是事件发生时间；Event ID 仍为 null。其余 FOX6、FOX9、USA TODAY、Fox Business、AP、NBC News、DawnNews、CNN 等仍为 metadata-only/相关报道线索，不可宣传为十个已核替代源。

## 事件发现模块与“为御注”最新澄清

用户新增原话（逐字）：

> “要分成多个模块,模块1 事件发现模块,周期运行,有一个源列表,excel 格式 可以手工或者自动添加,包含不限于 https://www.youtube.com/@WhiteHouse https://rollcall.com/factbase/trump/topic/calendar/ https://rollcall.com/factbase/trump/search/ https://rollcall.com/factbase/trump/topic/social/?platform=all&sort=date&sort_order=desc&page=1,  https://truthsocial.com/@realDonaldTrump https://gdelt.github.io/#api=doc&query=trump%20&contentmode=ArtList&maxrecords=250&sort=DateDesc&format=html&timespan=1w,https://polymarket.com/zh https://kalshi.com/ https://www.forth.news/whpool https://www.c-span.org/liveEvent/?president-trump-first-100-days  https://x.com/RapidResponse47 https://www.trumpstruth.org/stats,发现事件 总统出席几分钟 在哪里 说了几个单词,涉及哪些话题 你出一个表格有多列,和你提到的为御注,你可以泛化补充”

用户术语原话及最新澄清（逐字）：

> “为御注 意思是亲自提到的而链接 为御注 我在会话中亲自注解解释”
>
> “来源链接是用户在会话中亲自提到的，并由用户在会话中亲自注解/解释；不要解释成最高领导人亲自注解。事件来源表建议保存链接、用户在会话中的原注解/解释及其对应关系；之前将其释为“最高领导人亲自提及/注解”的归纳作废。”
>
> “你们乐意添加”
>
> “你们还可以加信息源包含不限于 https://www.forth.news/lists/trumpts一类”

记录者说明：以最新更正为准。“为御注”所指是用户在对话中亲自提供的链接及其亲自作出的注解/解释；此前误释为最高领导人亲自注解的归纳作废。字段建议为逐项链接、与链接对应的用户原始注解、引用上下文、发现时间、核验状态；未提供的逐源注解保持空白。用户允许扩充字段，但这不是新必填字段。

落实及边界（记录者归纳）：

- 新增 `config/event-discovery-sources.json`，逐字收录用户列出的 12 个来源 URL；来源可通过事件工作簿的 `Source Directory` sheet 手工增补，定时工作流会导入该 sheet、记下来源状态并重新生成 Excel/Pages。
- 将用户后来举例的 `https://www.forth.news/lists/trumpts` 作为第 13 个用户提议来源登记；页面可用性、覆盖、许可和可信度未独立核实，未接入自动抓取。
- 当前只有 White House YouTube 频道接入每日 metadata-only 自动 collector。Roll Call、Truth Social、GDELT Explorer、Polymarket、Kalshi、Forth、C-SPAN、X 与 stats 来源仅登记为待人工核验；没有声称已接入抓取、访问成功或许可审查。
- `Events` 和 `New White House leads` 工作表预留事件日期/时间/地点、总统实际出席分钟数、演讲词数及语言/统计方法、来源支持的话题、发现/核验时间、来源数量、置信度和用户注解等列。没有来源支撑的字段为空或标未核实。不能从上传日期、页面标题、预测市场活动或视频时长推定实际出席/发言数据。
- 工作簿 `User Instructions` sheet 保留上列用户原话及术语澄清；`Source Directory` 的用户链接逐项映射到原始来源列表，用户没有为某一来源单独写注解时，注解栏为空。此次只完成本地代码和数据结构的实现/验证，没有运行在线抓取、周期 workflow 或 Pages 部署。

## 2026-10-16 White House 视频轮询与逐视频研究

用户新增原话（逐字）：

> “可以定action runner 周期从白宫官方 获取视频 最小间隔获取,获取到后就开始全量研究每个视频”

落实要求及状态（记录者归纳）：

- 目标是在 GitHub-hosted Actions 上以最短可用周期（计划为每 5 分钟；实际启动可能受 Actions 队列延迟影响）轮询 White House 官方视频来源；使用稳定视频 ID 去重，并为每个新视频保存独立来源、时间及 workflow run 证据。
- 每发现一个新视频都要自动开始该视频的研究工作流。元数据搜索/来源页检索只是初始阶段，不能称为“全量研究完成”；须分别记录发现、元数据研究、源视频内容/音频画面核查和权利状态。
- 若某视频的帧/音频检查、下载或其他媒体步骤因缺少该视频专属授权或适用权利证据而无法继续，必须记录具体缺项并及时通知用户；不得静默跳过，也不得把元数据阶段伪称为完整研究。不能从定时轮询要求推断对所有视频的 blanket reuse rights。
- 任何媒体下载、探测、抽帧、ASR、渲染和编码都只能在授权 GitHub-hosted runner 上执行；不自动发布视频。来源、权利或内容状态保持真实记录，但不得成为获授权 pending Pages 更新的串行队列门槛。
- 2026-10-16 状态：PR [#62](https://github.com/gdelt0003/gdelt0003/pull/62) 已合并至 main（`d46f0596f03fadaf1ba36d74f5de870934abbcb3`），启用 GitHub-hosted 每 5 分钟轮询、稳定视频 ID 去重、独立 state branch/run provenance、官方 YouTube 页面 metadata 读取，以及每视频标题驱动的 GDELT article metadata 搜索。PR CI 通过，但首次真实 hosted run [38903661071](https://github.com/gdelt0003/gdelt0003/actions/runs/38903661071) 在采集前以 `ModuleNotFoundError: No module named 'scripts'` 失败，后续 run-file 持久化因文件未生成而失败；状态分支未建立。因此轮询、研究或 provenance 均尚未由成功 hosted run 验证。
- follow-up PR [#64](https://github.com/gdelt0003/gdelt0003/pull/64) 已合并至 main（`0f06644c50ab768d2241d5dc954e0ba324981f80`）：workflow 改用 `python -m scripts.monitor_official_whitehouse_videos`，并在持久化前显式验证 run/state 输出文件。聚焦 Python 测试 24 项通过、PR checks 通过。hosted run [38904287014](https://github.com/gdelt0003/gdelt0003/actions/runs/38904287014) 成功并写入 state branch/run JSON：因初始 state 为空，当前频道 100 项都被记录为新条目；100 项均进入媒体授权 gate。GDELT 查询 98/100 失败（78 HTTP 429、12 响应结构无 articles、6 非 JSON、2 timeout）；另外 2 项返回 12 条标题不相关的候选，0 条通过事件相关性筛选。没有媒体下载/检查。轮询及持久化已验证，但逐视频来源检索可靠性不足。
- follow-up PR [#65](https://github.com/gdelt0003/gdelt0003/pull/65) 已合并（merge SHA `a9872703ff917559ffb6e6f18367300696132a2e`；代码提交 `0d52c5a9361563432c56a624ae418e0d897f2583`），加入从持久 state 选择 oldest-first 失败查询、每次成功 run 最多重试 5 项、GDELT 并发最多 2、逐次尝试持久化以及 run summary 报告；20 个 monitor/workflow tests、4 个 GDELT tests 和 PR checks 通过。新 hosted 验证 run [38907411619](https://github.com/gdelt0003/gdelt0003/actions/runs/38907411619) 正在运行；需检查结果后再确认重试实际生效。无媒体处理/发布，也未放宽授权/权利门槛。
- PR #62 的监控记录会将缺少授权/权利时的 media review 标为 `not_started_blocked_waiting_for_authorization_and_rights`，并注明通知目前仅显示在 Actions run summary 与 warning annotations（不是外部推送）。
- PR #62/#64 已合并；hosted run [38904287014](https://github.com/gdelt0003/gdelt0003/actions/runs/38904287014) 已验证轮询、稳定 ID 去重和 provenance 写入，但 GDELT 搜索 98/100 失败，另两项的 12 条候选与标题不相关。候选文章页未打开或核验同一事件；事件时间/身份和权利仍未核验。流程不下载或发布视频；逐视频授权/权利缺项及待办状态只显示在 Actions run summary/annotations（没有外部推送）。失败查询的限量、低并发重试正在实现；任何媒体操作仍需精确视频授权和适用权利证据。
- 扩展 Rose Garden hosted search run [38902079023](https://github.com/gdelt0003/gdelt0003/actions/runs/38902079023) 在 PR #61 merge SHA `016dfd91f82ee8c6960dc61d136dae4af94ea13b` 成功：40 个 DuckDuckGo/Bing provider/query 组合、0 query errors，18 个去重 raw leads（9 irrelevant、9 landing-page metadata unavailable），0 个合格活动视频页；无视频媒体下载或检查。≥10 个独立相关发布页目标仍未达到。
- Rose 私有渲染 run [38895767927](https://github.com/gdelt0003/gdelt0003/actions/runs/38895767927) 已于 12:37:20Z 在旧 SHA `775c90e8f53aea473ef5556f0270d244e649e4b4` 失败：375/375 cue 翻译后，ASS geometry validator 报 cue 259；无 artifact。旧 run 不含 PR #59 merge 修复，且日志未说明失败的具体 geometry 子条件。先用代码/现有字幕证据诊断，不得本机下载/检查视频，也不得称为 cue overflow，除非证据支持。修复与 CI 通过后，依照用户指示准备 hosted rerender；但须先确保 exact video inputs 和适用的逐视频 rights/authorization evidence。
- cue 259 后续代码诊断发现并复现 ASS 时间精度不匹配：ASS 按 centisecond 保存时间，而 validator 对毫秒 cue 时间做精确比较。PR [#63](https://github.com/gdelt0003/gdelt0003/pull/63) 已合并为 `16b5ef69b6726fea616218b4840c8165334db1fb`，validator 允许最多 5 ms 的序列化舍入误差；这属于可复现的 validator bug，但失败 run 没有 artifact，故不能确认它就是 cue 259 的确切失败子条件。PR checks 与 main 上新触发的 checks 均通过；尚无后续 hosted rerender 验证。

## Rose Garden 字幕框坐标（用户更正）

用户原话（逐字）：

> “坐标是 **1920×1080** 画面中的横幅框，格式为 `[左, 上, 右, 下)`：**`[68, 885, 1850, 1020)`**。按每边外扩 2 px，字幕框是 **`[66, 883, 1852, 1022)`**，尺寸 **1786×139 px**。”

按此更正，`[68, 885, 1850, 1020)` 是横幅框；向每边外扩 2 px 后的 `[66, 883, 1852, 1022)` 是用户指定的字幕框，参考半开矩形尺寸为 1786×139 px（基准 1920×1080）。当前工作区把此参考框换算为相对视频宽高的比例坐标，再映射到实际帧分辨率；字幕居中于映射框内，若任一语言超过单行则拒绝渲染，manifest 记录参考框、归一化坐标、应用后的像素框/分辨率及待做帧审查状态。媒体源仍执行至少 1920×1080 的既有门槛，不做低分辨率放大。预览 workflow 还要求逐视频处理授权、精确事件匹配/事件时间确认及互不重复的 HTTPS 身份、匹配、时间、源到成片链路和权利证据；缺少任一确认或证据即在下载前失败。实现及测试尚未完成云端运行/实际成片帧验证，不等于已有视频按此坐标刻录。此前 main 上的渲染仍使用底部居中及百分比边距；失败的旧 hosted run 没有产物，PR #63 后没有成功 hosted rerender 证明该框已应用。

用户补充原话（逐字）：

> “把参考框按基准画面 1920×1080 归一化，再按实际视频宽高换算成像素坐标；这样同一字幕框可用于不同分辨率，不会把坐标硬编码到 1080p。//尽快开始渲染rose”

归一化换算对实际画面宽、高分别缩放参考框 x/y 坐标，采用四舍五入后的半开像素框；manifest 同时保存参考框、比例坐标和最终像素框。坐标换算不处理 letterbox/crop；若源内容存在黑边、裁切或非全画幅有效画面，实际字幕与横幅关系仍须由 hosted 渲染帧检查确认。静态坐标换算和单元测试不等于已开始/成功渲染 Rose 成片。
