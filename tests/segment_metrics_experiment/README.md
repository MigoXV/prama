# VAD 段级指标性能实验

后续状态：纯 NumPy 方案已进入 `src/prama/evaluator/vad.py`；以下保留原实验条件与结果，
正式接口及输入约束见项目根 README，正式回归测试位于 `tests/test_vad/`。

实验分支：`experiment/vad-segment-native`，从 prama 的 `dev`（`3e019e6`）创建。
全部代码、C 源码、结果和文档位于本目录；没有修改主程序、依赖清单或服务器工作区。
服务器基线为 `1bfc0be` 的 `src/prama_server/evaluator/vad/evaluator.py`。
实验直接导入实际服务器函数，源文件 SHA256 和环境记录在 `results.json`。

## 结论

原来的主要瓶颈是 Python 中参考段与预测段的两两比较（最坏 O(R×P)），
不是 NumPy 本身。`_segment_score` 还重复了一次参考段命中计算。
只把算法改成有序区间扫描，纯 Python 就能大幅提速；native C 能进一步减少匹配开销。
纯 NumPy 实现也已经很快，不一定需要增加 C 构建成本。

对 10 分钟合成 mask，完整计算从约 98.67 ms 降至纯 Python 扫描的 1.89 ms、
纯 NumPy 的 0.191 ms、NumPy+C 的 0.120 ms。后两者相差约 1.59 倍，
不能把相对旧实现的全部提升都归功于 C。
1 小时 mask 上，NumPy+C 比纯 NumPy 约快 1.29 倍；碎片化场景约快 3.72 倍。
保留 SciPy 连通域提取、仅换 C 匹配也有效，但随后提取段的成本占主导。

若将来接入主程序，可以先考虑 NumPy 的边界提取与向量化匹配；
确有高碎片度或高吞吐需求时，再考虑这里的 C 扫描。此次只做实验，没有接入。

## 实现与兼容性

| 版本 | 连续段提取 | 匹配 |
|---|---|---|
| original | 实际服务器 SciPy label/find_objects | 原 Python 两两遍历 |
| python_sweep | 相同 SciPy 实现 | Python 有序区间扫描 |
| numpy | NumPy 边界检测 | searchsorted + 重叠候选枚举 + maximum.at |
| scipy_c | 相同 SciPy 实现，转为 np.intp 数组 | C 有序区间扫描 |
| numpy_c | NumPy 边界检测 | 同一个 C 内核 |

C 通过 `np.ctypeslib.ndpointer` 接收 NumPy 的连续 `np.intp` 二维区间数组。
已有连续数组直接传指针；不经过 Python 逐元素复制，不引入第三方张量格式。
C 内核无动态分配、无可变全局状态，`ctypes.CDLL` 调用释放 GIL；并发只使用线程。
C 的私有区间接口要求输入有序、段内长度为正、同侧各段不重叠，
由 mask 提取函数保证；不能当作任意区间集合的通用接口。

端到端实验使用 `FunctionType` 创建原 `evaluate_masks` 的私有函数副本，只替换副本的
段提取/匹配函数。没有 monkeypatch 服务器模块，也没有改帧级计算、输入校验、
结果数据类及指标公式。为兼容 ndarray 的真假值判断，副本 `_segment_score`
使用 `len()` 检查空段集合，但仍保留原实现重复命中计算，以免混淆收益来源。

严格保留以下语义：

- 区间为左闭右开，端点接触不算正重叠。
- 参考段命中要求**某一个**预测段的交集长度/参考段长度达到阈值，不能累加多个段。
- 预测段只要和任一参考段有正重叠，就不算误报；不是一对一匹配。
- 阈值为 0 且目标段集合非空时，即使完全不重叠也算参考段命中。
- 浮点除法及比较顺序保持一致，没有使用 fast-math 或把除法比较改写为乘法。
- 原实现拒绝 squeeze 后为标量的单元素 mask；空 mask 在当前 SciPy 下抛出 ValueError。
  实验也保留这些行为，没有借实验修正业务语义。

## 实测

2026-09-26，Intel Xeon Gold 6326，Linux x86_64，Python 3.10.18，
NumPy 2.2.6，SciPy 1.15.3，GCC 14.2.0，C 使用 `-O3`，不启用 fast-math。
种子为 20260926，mask 由实验脚本生成，不是线上录音或真实预测结果。
时长名称按 10 ms 一帧解释；参考和预测分别生成，用于控制尺寸与段数。

每项预热后自适应批量计时，重复 5 轮，表中为中位数，单位 **ms**。
完整计算包含 Python 校验、段提取、数组转换、C 调用和帧级/段级所有指标，
不含首次编译、模块导入、ASR/VAD 模型推理、HTTP 和音频 IO。
这不是完整服务器请求延迟。各阶段独立测量，不要求相加等于完整耗时。

| 数据 | 帧数 | 参考/预测段数 | 原实现 | Python 扫描 | NumPy | SciPy+C | NumPy+C |
|---|---:|---:|---:|---:|---:|---:|---:|
| silence | 60000 | 0/0 | 0.7944 | 0.7920 | 0.0704 | 0.8350 | 0.0886 |
| 30s_sparse | 3000 | 22/21 | 0.6660 | 0.1959 | 0.0861 | 0.1938 | 0.0562 |
| 10min_sparse | 60000 | 305/303 | 98.6729 | 1.8857 | 0.1907 | 1.2995 | 0.1199 |
| 1h_sparse | 360000 | 727/735 | 572.6849 | 9.1853 | 0.6566 | 7.7044 | 0.5105 |
| fragmented | 4096 | 2048/1366 | 3020.3804 | 4.5244 | 0.2823 | 1.9137 | 0.0758 |
| all_speech | 60000 | 1/1 | 1.1186 | 1.1190 | 0.1368 | 1.1709 | 0.1114 |

| 1h_sparse 阶段 | 原实现 | Python 扫描 | NumPy | SciPy+C | NumPy+C |
|---|---:|---:|---:|---:|---:|
| 提取两个 mask 的连续段 | 6.9393 | 7.0558 | 0.2158 | 7.3373 | 0.2172 |
| 三次匹配调用 | 563.0562 | 1.7801 | 0.1569 | 0.0366 | 0.0362 |
| 完整 evaluate_masks | 572.6849 | 9.1853 | 0.6566 | 7.7044 | 0.5105 |

NumPy 只枚举实际重叠的候选区间，不创建 R×P 广播矩阵。
C 扫描匹配复杂度 O(R+P)；NumPy 还包含 searchsorted、向量分配及归约成本。
静音数据无需复杂匹配，NumPy+C 反而比纯 NumPy 略慢，C 并非所有输入都更快。

## 多线程吞吐

固定 64 个任务，复用已建立的线程池，计时包含提交和等待；单位 ms：

| 64 个 1h_sparse 任务 | 1 线程 | 2 线程 | 4 线程 | 8 线程 |
|---|---:|---:|---:|---:|
| numpy | 43.345 | 29.627 | 38.584 | 77.294 |
| scipy_c | 552.062 | 298.258 | 173.473 | 429.681 |
| numpy_c | 33.663 | 25.470 | 22.647 | 48.676 |

NumPy+C 在这台机器、这组负载下 4 线程约为单线程的 1.49 倍吞吐；
8 线程反而变慢。任务已缩短至亚毫秒，线程调度、Python 部分及内存访问开销都会影响扩展。
本次没有 CPU 绑核、没有排除机器上其他任务的影响，不能外推成线性加速承诺。
没有使用多进程。原始 5 轮计时、批量大小和每组 traced_peak_bytes 均保存在 results.json。
内存峰值由独立的一轮 tracemalloc 测量，不混入性能计时；它不是完整进程 RSS，
也不保证覆盖 SciPy/native 的所有分配，因此不把它当作泄漏判断。

## 正确性与内存检查

`validate.py` 五类测试通过：

- 穷举 5 帧二值 mask：1024 对输入 × 5 个阈值，比较所有结果数据类字段，使用严格相等。
- 300 组固定种子随机输入，同时覆盖逆序步长视图、可 squeeze 的二维形状。
- 0.9 及上下相邻浮点阈值边界。
- 输入类型、形状、空数组、单元素、非法阈值的异常类型与文本一致。
- 8 个线程共享同一 C 库，每个 C 后端运行 200 次，结果一致且只读输入未改变。

`check_native.c` 对照朴素 C 实现，10,000 组输入 × 4 个阈值 × 2 个方向，
ASan / UBSan / LSan 检查通过，没有报告内存错误或泄漏。
该 C 内核本身不分配内存；这不等同于对整个服务器做长期内存审计。
日志保存在 validation.log 和 native-validation.log。
主库 pytest 仍只收集原有 60 项，实验文件命名为 validate.py，避免给主库测试引入
服务器 NumPy/SciPy 依赖。

## 重现命令

使用服务器现有 Poetry 环境，不改任一项目的 TOML 或锁文件：

```bash
cd /workspace/test-bridge/prama-server
poetry run python /workspace/libs/prama/tests/segment_metrics_experiment/validate.py -q
poetry run python /workspace/libs/prama/tests/segment_metrics_experiment/benchmark.py
```

首次调用自动在实验目录编译带源码摘要的 `.so`，后续复用；产物被该目录 .gitignore 忽略。
检查源文件 SHA256 与 results.json 相同，可保证基线未漂移。
C 内存检查：

```bash
cd /workspace/libs/prama
cc -std=c11 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -no-pie \
  tests/segment_metrics_experiment/check_native.c \
  -o tests/segment_metrics_experiment/check_native.bin
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  tests/segment_metrics_experiment/check_native.bin
```
