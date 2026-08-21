# Jurisdiction Onboarding Prompt

Fill in what you know below, then hand this file to a Claude Code session opened in this repo — e.g. "read `jurisdiction-prompt.md` and set this up for us." You don't need to know any URLs, API schemas, or GIS terms; finding and verifying those live is the AI's job (see the `wildfire-likelihood` skill's "Onboarding a new jurisdiction" section, which it reads automatically). Leave anything you don't know blank rather than guessing — a blank tells the AI to go research it; a guess could send it down the wrong path.

## 1. Jurisdiction

- Province/territory name:
- What should the app be called (e.g. "Alberta Wildfire Predictor")?

## 2. Wildfire data source

- Name of the provincial/territorial wildfire agency, if known:
- Any open-data portal, map, or dashboard you've seen showing current fires (a link, or just "I've seen a map on their website" is enough):
- If you don't know of one, leave this blank — the AI will search for it and verify it's real before using it.

## 3. Branding (optional)

- Should this use the province's official visual identity (colors, logo, header)?
- If yes, do you know of a public design-system repo or brand guide? (If not, the AI will search for one before assuming it doesn't exist.)
- If no preference, the current BC Design System look stays as a placeholder, flagged as needing your jurisdiction's own branding.

## 4. Constraints — anything to keep, change, or drop

- Keep the AI-narrated advisory banner (the one-line plain-English summary)? [yes / no / not sure]
- Any other must-keep or must-not-do rules (e.g. "no AI-generated text at all," "must support French," "no logging of the search query")?

## 5. Who to ask if the AI gets stuck

- Name / how to reach you for anything the research can't resolve on its own (e.g. a data source that turns out not to exist, or an ambiguous naming choice).

---

*This file is the input. The actual research-and-wiring steps this prompt triggers are documented in `.claude/skills/wildfire-likelihood/SKILL.md`, under "Onboarding a new jurisdiction" — read that section to see exactly what the AI does with what you fill in above.*
