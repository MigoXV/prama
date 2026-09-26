# sclite 重建与验证记录

验证日期：2026-09-26。分支：`feature/sclite-native-streaming`。

## 构建产物

执行了真实的 `poetry build`，不是仅测试源码。当前 wheel 面向 CPython 3.10、Linux x86_64；动态符号需要 glibc 2.33 或更新版本。运行时仅依赖系统 libc、libm 和动态加载器，无开发目录 RPATH，无旧 `.so` 依赖。其他 Python/系统环境请从 sdist 重建。

| 产物 | SHA-256 |
| --- | --- |
| `prama-0.1.0a1-cp310-cp310-linux_x86_64.whl` | `7e71c4de18b44815d8e9111cb77a36c0f745144030549bab4e5a788635d7be7b` |
| `prama-0.1.0a1.tar.gz` | `0918ac7be137208489261840986738743bf7071c10a55186c5e0d4e7aa7afa4a` |

两套独立 Poetry 环境分别安装原始 wheel 和从 sdist 重建的 wheel。测试前清除 `PYTHONPATH`、`SCLITE_LIB_PATH`，从仓库外运行，并断言包和动态库来自安装目录；消费者的 `CC` 被设置为不存在的路径，以检查运行时不需要编译。两个环境均通过 **60 项测试**及 **10,000 对数据的 WER/CER 对照**。分发包内源码和当前工作树逐文件核对一致。

详细构建记录：[verification.log](../outputs/distribution/verification.log)，产物哈希：[result.json](../outputs/distribution/result.json)。

## 算法与接口

基准来自未修改的 SCTK 提交 `9688a26882a688132a5e414cadcb4c19b6fffaba`，使用关闭 GNU diff 和 SLM 的构建配置。

固定种子 `20260926` 生成 10,000 对文本，在 WER、CER 两种模式下分为 200 个批次验证。每批比较新库批量、流式最终结果、逐条事件与原版 CLI 的 SYS、RAW、PRA、PRF、SGML 报告，共 1,000 次 CLI 报告比较。只规范化输入文件路径和生成日期。

额外测试覆盖上游语料、TRN/TRN、STM/CTM、CTM/CTM、分词推断 algo1/algo2、词权重、可选删除、片段匹配、Unicode、空文本、长 ID、异常恢复和提前关闭。

旧 `.so` SHA-256：`6afbbd6d50f8a7a3c7238a5d5de938fd45bfe6afdecc2ce4e99919856a88c241`。200 批中有 199 批的旧库 SGML `sequence` 跨调用累加，与原版 CLI 每次从零开始不同；除此以外，所测数据的旧库计数、元数据、token 和报告一致。该差异有独立分类，没有用于放宽原版验收。

详细记录：[differential.json](../outputs/differential.json)。

## 多线程与资源安全

原生可变状态使用线程局部存储。并发测试用屏障让多个工作线程同时停留在原生回调中，检查不同选项、慢消费、单任务取消及跨线程读取/释放。没有用多进程替代多线程。

| 检查 | 规模 | 结果 |
| --- | --- | --- |
| ASan / UBSan / LSan 生命周期 | 10,000 轮成功、报告、取消、失败 | 通过 |
| ASan / UBSan / LSan 并发 | 8 线程 × 1,250 轮 | 通过 |
| ASan / UBSan / LSan 上游格式与选项 | 10 组，含报告和取消 | 通过 |
| Valgrind Memcheck 生命周期 | 10,000 轮，17,762,064 次分配/释放 | 0 错误，退出时 0 字节残留 |
| Valgrind Memcheck 并发 | 8 线程 × 100 轮 | 0 错误，退出时 0 字节残留 |
| Valgrind Memcheck 上游语料 | 10 组 | 0 错误，退出时 0 字节残留 |
| Helgrind | 8 线程 × 100 轮 | 0 错误，使用工具默认系统库抑制规则 |
| Python 线程与文件描述符 | 200 次流创建与提前关闭 | 无残留工作线程、描述符数量不变 |

修复了测试中发现的权重列初始化缺失和零长度空指针 `memcpy`；同时处理长 ID 缓冲扩容、有界格式化、字符比较临时缓冲和异常资源回收。保留完整结果导致的内存占用属于对象生命周期内的正常持有，不等同于泄漏。

日志见 [valgrind-final.log](../outputs/valgrind-final.log)、[thread-valgrind.log](../outputs/thread-valgrind.log)、[corpus-valgrind.log](../outputs/corpus-valgrind.log)、[helgrind.log](../outputs/helgrind.log)、[final-sanitizers.log](../outputs/final-sanitizers.log)、[thread-sanitizers.log](../outputs/thread-sanitizers.log)、[corpus-sanitizers.log](../outputs/corpus-sanitizers.log)。这些结果说明本次覆盖范围内未发现未解决的内存或线程错误。

## 复现命令

```bash
poetry install
poetry run python scripts/build_reference.py
poetry run python build_native.py
poetry run pytest
poetry run python scripts/check_alignment.py --cli build/original/sclite/sclite --count 10000
poetry run python scripts/check_native.py
poetry run python scripts/verify_distribution.py
```

原生检查需要 GCC 和 Valgrind。验证脚本应顺序运行；分发验收会为干净构建移除项目生成的 `.so`，此时不要同时运行依赖开发目录动态库的测试。
