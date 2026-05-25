# Preference tuning notes

Preference/RL comes after `v0-sft-main`, not before.

Use preference data when SFT has the right output shape but inconsistent choices.

## Good pair targets

- compact correct trace vs verbose wandering trace
- correct tool/action vs plausible wrong action
- verified success claim vs unverified success claim
- acts on obvious default vs unnecessary clarification
- concise final vs padded final

## Candidate methods

- DPO / ORPO / SimPO for chosen/rejected pairs.
- Rejection sampling + SFT for cheap/simple improvement.
- GRPO only when reward is programmatic and hard to game.

## Rule

Do not start RL until v0 SFT is boringly good on the held-out Hermes eval.
