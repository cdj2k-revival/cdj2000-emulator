# SH-4 MAIN translation fast paths (2026-10-05)

`patches/qemu-sh4-tcg-fast-paths.patch`, adapted from Stijn Jacobs'
cdj-nxs2-qemu (see `patches/README.md` for the knobs). Profiled first, on
stock NXS with `--dsp-model` and a real rekordbox USB export, boot -> Not Loaded, USB mount, browse,
Enter -> loaded, with macOS `sample` on the QEMU process and the ported
`CDJ_JCPROF`.

What the profile said (TCG thread, unpatched):

* The vCPU never idles: MAIN's idle state is a busy loop, ~50 % of sampled PCs
  in `strlen` (`0x04388e48`) and `strncmp` (`0x04388500`) called from
  `0x04311438..0x0431144e`. TB lookups ran at ~35 M/s, split evenly between
  `jsr` and `rts`, with 99.6 % jump-cache hits: the cost is the
  `helper_lookup_tb_ptr` call itself (12-15 % self, 18-21 % inclusive), not
  qht misses.
* Stores into pages holding code: `notdirty_write` ->
  `tb_invalidate_phys_range_fast` was 11 % of the boot-phase thread
  (`page_collection_lock`, QTree, malloc), and 8.5 M such stores in a run
  overlapped no TB at all.
* MMIO dispatch (~4 %), `cpu_io_recompile` (<1 %), `helper_ld_fpscr` (1 %) and
  lock waits (3 %) were minor.

Throughput, MAIN alone under `-icount shift=2,sleep=off` (4 ns per
instruction, so guest seconds per host second is instruction throughput),
same firmware, card and `CDJ_NXS_DSP_MODEL=1`, 30 host seconds:

| build | guest s / host s (30 s) | host s to guest 1 s | to guest 32 s |
|---|---:|---:|---:|
| before (two runs) | 4.38, 4.62 | 1.66, 1.66 | 7.98, 8.23 |
| after (three runs) | 5.51, 5.31, 5.38* | 0.85, 0.86, 0.86 | 6.40, 6.43, 6.68 |
| after, all knobs =0 | 4.67 | 1.66 | 8.24 |
| after, `CDJ_SMC_FASTREJECT=0` | 4.56 | 1.66 | 7.97 |
| after, `CDJ_TB_XPAGE=0` / `CALLPRED=0` / `FPSCR=0` | 5.34 / 5.14 / 5.23 | 0.85-0.87 | 6.67-6.68 |

(*the third "after" run included a since-removed return-prediction
experiment.) The store fast-reject is the large term: the first guest second
of boot halves (1.66 -> 0.86 s) and the run gains ~15-20 %; call prediction,
cross-page chaining and FPSCR chaining are a few percent each, at the noise
floor of this busy host. With `CDJ_JCPROF`, `jsr` lookups fall from 428 M to
17 M per run.

Milestones, full two-board scenario (wall seconds; boot from launch to the
`Not Loaded.` screen, mount from the USB key to the USB browser, Enter ->
loaded to the command-5 duration reply), `--gui-head-start 2.0`, alternating
runs:

| build | boot | mount | browse | Enter -> loaded | QEMU CPU s (whole run) |
|---|---|---|---|---|---|
| before (4) | 7.31-7.65 (7.44) | 0.27-0.29 | 0.27-0.28 | 0.86-0.92 | 24.6-25.0 |
| after (4) | 6.81-7.86 (7.23) | 0.27-0.29 | 0.27-0.28 | 0.87-1.08 | 22.8-24.4 |

With `--dsp-model` none of these is bound by SH-4 speed: mount and load are
sub-second either way and boot is set by the simulated GUI and the link
handshake, so the gain shows as throughput, not latency. The Not Loaded and
USB-browser screens are byte-identical between builds; the loaded screen
matches outside the blinking NOW LOADING text in every run where it was not
mid-redraw (one in four for both builds).

# C674x interpreter performance

The NXS DSP interpreter runs synchronously inside the SH-4's MMIO path, so its
speed bounds the whole emulated machine. These changes make it faster without
changing what it computes: every one keeps traces, events and DSP checkpoints
byte-identical to the previous build.

## Changes

* **Decode memo.** Row selection in the 114-row conditional dispatch table is
  a pure function of the instruction word (`also` predicates read only the
  word; see `cdj_c674x_arm_table_predicates_are_word_only`), so
  `cdj_c674x_arm_lookup` memoizes it per word in a direct-mapped table of
  relaxed 64-bit atomics (word and row in one entry).
* **In-place packet execution.** Each packet used to run against a scratch
  copy of the 3 KB CPU prefix that was copied back on success.
  `cdj_c674x_execute` now backs up the scalar prefix and live queue entries,
  runs the packet (`execute_packet`) directly on the CPU, and restores the
  backup if it fails. Queue appends go through `append_load`/`append_store`,
  which save the overwritten slot first, so a rollback leaves exactly the bytes
  a discarded copy would. `cycles` and `packets` still change only when the
  packet retires, because bus callbacks read them mid-packet. The old copy
  transaction remains behind `CDJ_C674X_COPY_TRANSACTIONS`, and
  `tests/test_c674x_transaction.py` builds it as the byte-exact reference
  (with cases where an append is followed by a rejected parallel instruction).
* **Loop-buffer transactions.** `loop_step` copied 5.2 KB in and out on every
  loop-buffer cycle. A sealed loop step now copies only the scalar prefix, live
  queue entries and the loop's scalar fields, reads the committed tags/count
  schedule through `cdj_c674x_loop_issue_*_from`, and commits queue slots up to
  the extent execute reports writing. SPLOOP setup stops short of the
  instruction buffer, and the IDLE/padding path executes in place.
* **Fetch block hook.** `cdj_c674x_set_fetch_block` lets a board return a host
  pointer to a whole 32-byte fetch block of plain memory, replacing one read
  callback per instruction word. Nothing is cached across fetches, so code
  writes stay visible. The NXS board and the replay tool register it.
* **Per-cycle and per-read trims.** Timers with both ENAMODE fields clear are
  skipped (the NXS boot never enables them); the SPI tick has an exact idle
  fast path and no per-cycle division; the PLL tick skips its division when no
  whole input period elapsed; `cdj_c674x_loop_functional_timing()` is inline;
  the NXS `dsp_read` tests L2 first (the windows are disjoint and firmware
  executes from L2); the issue loop reuses the pre-scan's NOP/SPMASK decode;
  and the queue scans skip entries that cannot act this cycle.

## Measurements (macOS, Apple silicon)

Same QEMU tree and toolchain, `upstream/main` against this branch, 60-second
full-capture NXS boots through `tools.cdj_main.nxs_vm`:

| Boot | DSP packets, upstream | DSP packets, this branch | Events / checkpoints compared |
| --- | ---: | ---: | --- |
| default | 406M | 654M | 118,238 / 446, all identical |
| `--functional-dsp-audio` | 377M | 603M | 117,165 / 417, all identical |

Standalone replay (`tools/cdj_dsp/replay.c`): boot checkpoints give identical
traces and final checkpoints; 5M steps of a mid-playback snapshot with
functional audio take 1.18-1.20 s upstream and 0.68-0.69 s here, with an
identical trace and final checkpoint.

The pytest suite gives the same result on both builds (680 passed; the same
26 checkpoint/deferred-replay tests fail on `upstream/main` in this
environment).

## Persistent packet cache and fast paths (2026-10-05)

Ideas after Stijn Jacobs' cdj-nxs2-qemu (its `c66x_step.c` packet cache and
`fast_cycles`, and its `make m1` decoder sweep), used with permission; credit
in THIRD_PARTY.md, no code copied. All of it is in `emulator/qemu/cdj_c674x.c`;
no board file changed. This supersedes "Nothing is cached across fetches"
above.

* **Decode record.** Everything the issue loop derived from an instruction
  before touching state (pre-scan NOP/SPMASK, compact lowering, CALLP,
  DINT/RINT, unconditional class, arm row, and the compact format, now
  `compact_form()` in the issue loop's test order) is one pure function,
  `decode_instruction`. Uncached packets decode on the fly with it.
* **Packet cache.** Per thread, direct-mapped on pc/2 (16K entries), for
  direct steps: fetched packet, decode records, fast-path eligibility.
  Invalidation is by content: an entry keeps the raw 32 bytes of every fetch
  block its fetch read, and each hit re-obtains them through the board's
  fetch-block hook and compares. DSP stores, HPI uploads, EDMA, L1D/SDRAM
  remaps are all seen at the next fetch with no hook in any writer; words
  that came through the read callback are never cached.
* **Fast path** (`execute_fast`) for cached packets that write no control
  register during issue: execute in place with no prefix copy. E1 register
  results are deferred until issue has passed every check
  (`CdjC674xDefer`), so a failing packet is declined byte-for-byte and the
  transactional path reproduces the fault. Retirement can fail only on a
  queue entry, so registers, control registers and live queue entries are
  snapshotted only when an entry can act within the packet; such a fault is
  restored as the transactional rollback would leave it (retirement faults
  now report the packet's entry pc, which is what they always reported).
* **Single-instruction path** (`execute_single`), ~90% of NXS packets: one
  register-only arm (MVK/MVKH/ADD/SUB/AND/OR/XOR/CMP/shifts/bit fields/MVC
  read...), B, B reg or NOP n, when no queue entry acts in its cycles.
* `CDJ_C674X_PACKET_CACHE=0` disables all of it, `=decode` keeps only the
  cache; `cdj_c674x_set_packet_cache()` does the same for tests.

Not done: the per-hit fetch-block call (`dsp_memory_span`, ~7% of the DSP
thread in a profile) could go if the board declared mapping-stable windows; McASP-paced
batching of NOP runs needs board cooperation (each cycle ticks the board).

### Exactness

* Same QEMU binary, `CDJ_C674X_PACKET_CACHE=0` against default, 45-second
  full-capture stock NXS boots: all 214,401 events and 3,045 DSP checkpoints
  of the common prefix byte-identical; with `--functional-dsp-audio`,
  121,309 events and 529 checkpoints. Final screens identical. Against the
  pre-change binary: 234,677 events and 3,593 checkpoints identical.
* Replay (`tools/cdj_dsp/replay.c`): checkpoints 1, 25, 250 (1M steps), 400
  (5M) and the first-play snapshot (5M, strict and functional audio) give
  identical traces and final checkpoints against the pre-change core, and
  cache off against on.
* `tests/cstub/c674x-packet-cache.c`: 3,000 random programs (self-modifying
  stores, host code rewrites between steps, fetch-window withdrawal, failing
  store commits and E3 reads) run in lockstep cached+fast vs uncached;
  whole CPU and memory compared after every step (3.4M packets, 1,977
  faults). Removing validation, the register/branch/slot rollback, the
  deferral, the entry-pc fault, the single path's window or predicate, or
  its branch break each fails it. Clean under ASan/UBSan.

### Measurements (Apple silicon, loaded shared host)

| Workload | Before | After |
| --- | ---: | ---: |
| `benchmark_core` step-alu, 30M packets | 21.3 M/s | 77 M/s |
| `benchmark_core` step-mem (LDW/STW loop) | 19.1 M/s | 37 M/s |
| replay ckpt 400, 20M steps, user s | 2.20-2.21 | 1.70-1.71 |
| replay first-play, functional audio, 5M | 0.67-0.68 | 0.56-0.57 |
| 60 s NXS boot, DSP packets | 649M, 648M | 844M, 857M |
| same, `--functional-dsp-audio` | 585M | 737M |
| same binary, cache off vs on | 603M | 852M |

Boots ran pairwise at the same time on a loaded host, with
`--lightweight`, so no capture cost. With the core cheaper, the DSP thread
is now roughly half board work (`dsp_cycle_tick`, timers, PLL, interrupt
delivery), which bounds further core-only gains.

## Decoder cross-check (2026-10-05)

`tools/cdj_dsp/decode_crosscheck.c` sweeps an address range from a DSP
checkpoint through `cdj_c674x_fetch` and `cdj_c674x_describe` (the family the
issue loop executes); `python -m tools.cdj_dsp.decode_crosscheck` compares
it with GNU objdump (`gobjdump -D -z -EL -b binary -m tic6x`): instruction
boundaries and sizes, parallel bits, family vs mnemonic, and every compact
instruction the core rewrites to 32 bits re-disassembled from the rewritten
word. Over the NXS stage1 (0x11801da0-0x11804d80) and stage2
(0xc0000000-0xc0058320) images: 90,273 instructions, 1,582 rewritten compact
operands, 0 disagreements; the only fetch rejections are 818 blocks of
0xffffffff fill that objdump also calls undefined. Operands of in-place
compact forms and of 32-bit arms are outside this check.
