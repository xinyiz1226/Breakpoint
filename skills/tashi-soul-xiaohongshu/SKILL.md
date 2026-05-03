---
name: tashi-soul-xiaohongshu
description: Create TASHI SOUL Xiaohongshu posts, titles, cover copy, short Chinese body text, image scripts, text-free background image prompts, typography guidance, tags, and risk-word replacements. Use when the user asks for TASHI SOUL brand content, Xiaohongshu notes, Tibetan-incense brand storytelling, calm culture-led Chinese social posts, or visual prompt planning for this brand.
---

# TASHI SOUL Xiaohongshu

## Workflow

Use this skill to draft Xiaohongshu image-text notes for TASHI SOUL with a calm, restrained, culture-led voice.

1. Clarify or infer the content brief: topic, purpose, product exposure level, target reader, emotional pain point, philosophy direction, image count, visual direction, composition, and extra constraints.
2. Read [brand-voice.md](references/brand-voice.md) before writing unless the user only asks to revise an already-generated post.
3. Use [input-template.md](references/input-template.md) when the user wants a reusable prompt or has not provided enough brief details.
4. Use [sample-post.md](references/sample-post.md) as a tone and structure reference when matching the expected output format.
5. Produce the complete output in Chinese unless the user asks otherwise.

## Default Stance

Treat TASHI SOUL as the spiritual source of the content, not as the visible subject.

- Default to brand-led content, not product-led content.
- Do not mention incense, product benefits, purchase reasons, ingredients, or the TASHI SOUL name unless the user explicitly asks for product exposure.
- When product exposure is requested, keep it quiet and contextual: write the person first, then the incense as one part of a life ritual.
- Never promise medical, sleep, luck, energy, magnetic-field, blessing, or life-changing effects.
- Do not turn Tibetan Buddhism, religious objects, or Tibetan culture into novelty, mysticism, authority, or sales leverage.

## Required Output

Return these sections for a standard note:

1. `【选题洞察】`: 1-3 sentences about the urban emotion and content angle.
2. `【产品露出判断】`: whether incense, product, or brand name should appear.
3. `【标题】`: 7 Xiaohongshu titles grouped as 2 resonance, 2 story, 2 light-philosophy, and 1 save-worthy title.
4. `【封面文案】`: 3 short lines, each under 18 Chinese characters.
5. `【正文】`: one 120-200 Chinese character post built from a small life scene, emotional turn, gentle observation, and lingering ending.
6. `【图片脚本】`: 3-6 images unless the user specifies otherwise; include background direction, scene, composition or dark text area, text line, and typography form.
7. `【图片生成 Prompt】`: text-free background prompts with low-saturation Tibetan natural or humanistic atmosphere, clear blank/dark text area, no logo, no product, no text.
8. `【图片文字排版建议】`: where and how to overlay text, font mood, color, and separators.
9. `【标签】`: 8-12 Xiaohongshu tags.
10. `【风险词替换】`: risky expressions to avoid and softer alternatives.

## Writing Rules

- Write people before ideas, and scenes before viewpoints.
- Keep the story small: commute, late-night living room, parking garage, dinner aftertaste, meeting pause, family friction, insomnia, silence.
- Use ordinary language to translate ideas such as impermanence, letting go, observation, causes and conditions, compassion, emptiness, silence, acceptance, and non-attachment.
- Avoid cheap virality, hard selling, fear, forced empathy, exclamation marks, commands, and exaggerated promises.
- Avoid claiming or implying quotes from specific books or religious sources unless the user provides exact source material and asks for it.

## Visual Rules

Generate background prompts separately from typography guidance. The background prompt should not ask the image model to render Chinese text.

Prefer:

- Tibetan natural elements: quiet lakes, distant snow mountains, plateau clouds, valley mist, stone, wind, grass, mountain shadow.
- Tibetan humanistic elements: monastery wall corners, prayer wheels, distant prayer flags, walking backs, hand turning a prayer wheel, quiet temple corners.
- Minimal, cool, deep, restrained, low-saturation visuals with spacious blank areas and a clear dark text zone.

Avoid:

- Giant frontal Buddha imagery, oppressive religious symbols, gold light, miracles, energy fields, tourist-promo style, commercial poster style, internet celebrity filters.
- Product visuals unless the user explicitly requests product content.
