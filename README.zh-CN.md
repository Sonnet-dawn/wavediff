# wavediff

**找出两次仿真波形第一个不一样的时刻。**

不用再对着两个 GTKWave 窗口用肉眼扫描。把 golden 波形和新的波形交给
`wavediff`，它会直接告诉你**第一个分歧发生在哪个时刻、哪个信号**——既能作为
CI 退出码，也能生成一份可以直接贴进 PR 的报告。

[![ci](https://github.com/Sonnet-dawn/wavediff/actions/workflows/ci.yml/badge.svg)](https://github.com/Sonnet-dawn/wavediff/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

*[English](README.md) · 简体中文*

---

## 痛点

你改了 RTL，重跑了测试，测试还是"过"的。但你想知道的是：**除了你改的地方，
还有什么跟着动了？**

能回答这个问题的工具只有 Verdi 和 SimVision——比你的笔记本还贵，而且只读
FSDB。

于是"波形的 `git diff`"一直是缺失的一环，大家的土办法是：人工盯着两个同步的
波形窗口，找那根位置不对的跳变沿。这有三个必然结果：

- **慢**：每轮回归、每个信号都要花上几分钟
- **不可靠**：真正有意义的变化通常在屏幕外
- **CI 看不见**：没有退出码、没有产物、没有可以 review 的东西

`wavediff` 就是那条缺失的命令。

## 效果

```console
$ wavediff examples/golden.vcd examples/regressed.vcd --html diff.html

A: examples/golden.vcd
B: examples/regressed.vcd
alignment: absolute timestamps (mode=auto)

DIVERGED  first difference at t=36 (1ns); 2 differ, 3 match, 0 only in A, 0 only in B

  t=36         tb.dut.result                            A=00110010     B=00111111     (1 interval(s))
  t=66         tb.dut.valid                             A=0            B=1            (1 interval(s))

HTML report written to diff.html
```

一条命令定位了两处回归：

1. **`t=36`** —— 第一个出现差异的时刻，而不是"在这 50 MB 里的某处"。
2. **`tb.dut.result` 和 `tb.dut.valid`** —— 带层次路径的信号名，可以直接贴进波形
   查看器或 bug 单。同时报告也明确说明 `tb.dut.state`、`tb.clk`、`tb.rst_n`
   没有变化，而不是让你自己去推断。
3. **给出的是区间，而不只是一个点** —— `result` 从 `t=36` 错到 `t=46`，`valid`
   从 `t=66` 错到 `t=76`。一个单周期毛刺和一根卡住的控制信号是完全不同的 bug，
   报告会区分它们。

HTML 报告会把每个分歧信号的两版波形都画出来，并把分歧区间标红：

![wavediff 生成的 HTML 差异报告，显示两个分歧信号](docs/demo.png)

这份报告就是 `docs/demo.html`——单文件、内联 SVG、无脚本、无网络请求，所以无论
从邮件附件还是共享盘打开都能正常显示。十秒钟即可自己复现：

```bash
git clone https://github.com/Sonnet-dawn/wavediff && cd wavediff
PYTHONPATH=src python -m wavediff examples/golden.vcd examples/regressed.vcd --html diff.html
```

```console
$ wavediff golden.vcd regress.vcd        # 人读格式，有差异则退出码为 1
$ wavediff golden.vcd regress.vcd -q     # 静默，CI 模式
$ wavediff a.vcd b.vcd --json out.json   # 机器可读
```

## 安装

```bash
pip install git+https://github.com/Sonnet-dawn/wavediff
```

<!-- 待办：PyPI 发布上线后，把上面这行换回 `pip install wavediff` 并删掉本注释。 -->

**零依赖**，纯 Python 标准库实现。只读 VCD，不需要编译，也不需要任何 license。
用这种方式安装只会拉进 `wavediff` 本身，没有任何间接依赖。

## 关键难点：两条时间轴本来不可比

这是 `wavediff` 没有停留在"50 行脚本"的原因。

两次"同一个" testbench 的 dump，**没有保证的共同时间原点**。你插了一级流水线，
B 里所有下游跳变就整体晚一个周期。此时朴素的 diff 会报出几百处差异，而真正的
功能改动只有一处——工具立刻变成噪声，然后你就不会再打开它了。

所以对齐是**显式**的，而且永远会打印在报告里供你核对：

| `--align` | 行为 | 适用场景 |
|---|---|---|
| `none` | 完全按绝对时间戳比较 | 小改动，时间原点一致 |
| `auto`（默认） | 对所有共有信号**投票**推断偏移量 | 不确定两条时间轴是否对齐 |
| `shift --shift N` | 给 B 整体加固定偏移 `N` | 你已知延迟差 |
| `reference --reference SIG` | 让指定信号的首次跳变与 A 对齐 | 你有一个可信的参考时钟/复位 |

`auto` 被刻意设计得很保守——**不会**因为单个信号就整体平移时间轴，并且在票数
相同时保持不动，因为平移时间轴是一种破坏性操作：

```console
$ wavediff golden.vcd shifted.vcd
alignment: B shifted by -10 time units (mode=auto, 4/4 shared signals agree on offset -10)
IDENTICAL  (4 signals compared, no differences)
```

> **为什么用投票而不是单个参考信号？** 见
> [`docs/design.md`](docs/design.md)：对齐模型、为什么 `t=0` 的状态不参与投票、
> 以及完整推导。

## 用在 CI 里

退出码就是契约：

| 退出码 | 含义 |
|---|---|
| `0` | 在选定对齐方式下完全一致 |
| `1` | 有分歧——至少一个信号不同，或只存在于其中一个文件 |
| `2` | 无法完成比较（文件或参数有问题） |

```yaml
- name: 与 golden 波形对比
  run: |
    wavediff golden/${{ matrix.test }}.vcd artifacts/${{ matrix.test }}.vcd \
      --align auto --html diff.html --json diff.json
- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: waveform-diff
    path: diff.html
```

上传的 `diff.html` 本身就是完整的 bug 报告：单文件、内联 SVG、无脚本、无网络
请求，所以无论从邮件附件还是共享盘打开都能正常显示。

## 为什么不直接用现有工具？

| 工具 | 结论 |
|---|---|
| **Verdi / SimVision** | 能 diff FSDB，但按席位收费。`wavediff` 免费、读 VCD、能在 CI 里无头运行。 |
| **GTKWave** | 优秀的查看器，但"比较两个文件"至今仍是[未实现的需求](https://github.com/gtkwave/gtkwave/issues/315)。`wavediff` 生成一份报告，而不是让你去盯着看。 |
| **`diff a.vcd b.vcd`** | 比的是 dump 的**文本**。变量 id、前导零、时间戳格式在两次运行间都不同，噪声会把答案彻底埋掉。 |
| **`vcddiff`** | 十多年前的脚本，没有对齐模型，也没有报告。 |

## 范围与局限

把边界讲清楚比过度承诺有用：

- **目前只读 VCD**。FST / GHW 在[路线图](docs/roadmap.md)上；FSDB 是专有格式。
- **目前是 Python 解析器**。单遍前向扫描对常见的 testbench dump 足够快，但几十
  GB 的波形需要路线图里的原生后端。解析器已经是单一入口（`read_vcd`），所以编译
  核心可以直接替换进来而不动对齐、diff 和报告。
- **diff 是精确的，不是采样的**。它比较跳变事件流，因此在任何时间精度下都正确，
  复杂度是 `O(跳变数)` 而不是 `O(时长 / 步长)`。

## 作为库使用

```python
import wavediff

a = wavediff.read_vcd("golden.vcd")
b = wavediff.read_vcd("regress.vcd", signals=[r"^tb\.dut\."], max_time=10_000)

result = wavediff.diff(a, b, mode="auto")

if not result.identical:
    print(f"首个分歧时刻 t={result.first_divergence}")
    for sig in result.differing:
        for run in sig.runs:
            print(f"  {sig.name}: {run.describe_time()}  {run.value_a} -> {run.value_b}")
```

## 开发

没有依赖，也没有要学的框架——测试就是标准库 `unittest`：

```bash
git clone https://github.com/Sonnet-dawn/wavediff
cd wavediff
PYTHONPATH=src python -m unittest discover -s tests -t tests -v
```

欢迎贡献。最有价值的两种 PR 是：**让解析器崩溃的 VCD 文件**，以及
**`auto` 对齐选错偏移量的波形对**——两者都会被收进 `tests/fixtures/` 作为回归用例。

## 许可证

[Apache-2.0](LICENSE)
