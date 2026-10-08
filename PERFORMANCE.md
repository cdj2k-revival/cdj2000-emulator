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
