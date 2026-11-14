# Playtest: <card title in plain words>

**Time:** ~<N> min · **Where:** <desktop | headset | emulator | dashboard> · **Card:** #<id>

## What changed
<2-3 plain sentences a player would understand. No internal names, no file paths, no test jargon.>

## Setup
1. <exact copy-paste command or click, one per line>
2. <...>

## Do this, and expect
1. <one action> → **Expect:** <what you should see, hear or feel>
2. <...>
<!-- 3-8 steps. Each step is one action with one observable expectation. -->

## Pass if
- <observable outcome, e.g. "an open 3-pointer goes in about 1 in 3 times; a contested half-court heave almost never">

## Fail if
- <observable outcome that means "send it back", e.g. "any shot from half-court goes in more than once in 5 tries">

## Tell me
Reply in chat with **pass**, **fail: <step number and what happened>**, or **unsure: <why>**, plus:
- <1-3 specific questions, e.g. "Did the debris stun feel readable at full speed?">

## Already checked for you
<one line: what automated checks covered, so you don't repeat them>

<!--
Rules for whoever writes this (Codex at review pass, Claude or the conductor in chat):
- Expert clarity, plain language. The producer is the expert on fun, not on our internals.
- At most ~25 bullets in total. Aim for 10 minutes or less. Split anything longer into two playtests.
- Every step has an observable expectation. Every pass/fail line is something the producer can see.
- VR projects: say whether the headset is needed. If it is, put headset setup first.
- Rollback, budgets and process notes go in BUILD_NOTES.md, never here.
-->
