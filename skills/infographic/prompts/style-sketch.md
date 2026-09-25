# Стиль «карандашный скетч-шедевр» — блоки промпта для genimage

Разобран на эталонах NotebookLM (слово владельца 25.09.2026): каждая страница эталона —
ОДНА картинка целиком от модели, текстовых полей нет. Модель по умолчанию `gemini-3-pro`
(`google/gemini-3-pro-image-preview`): даёт те же размеры, что у эталона (768×1376 и 1376×768
при 1K), держит русский и узбекский текст. Запасная — `gpt-5.4-image-2`.

Промпт = блок стиля (не менять) + блок тона + разметка страницы + точный текст.

## Блок стиля — в каждый промпт без изменений

```
Professional pencil sketch, masterpiece, hand-drawn graphite linework on warm cream paper,
subtle cross-hatching, fine architectural blueprint annotations (ruler tick marks, crosshairs,
torn deckle paper edge), clean legible hand-lettered headings printed in bold sans-serif
(NOT cursive) for titles, small italic handwritten-style script only for short secondary
captions, generous white space, no photorealism, no 3D render look, nothing cropped or cut
at the edges, generous margins.
```

## Блок тона — выбрать один

**Учебный, для людей** (урок, пост, объяснение продукта):
```
Muted sepia and teal accent tones. Friendly and clear, simple metaphors are welcome
(a road with steps, rings, a staircase, a small hand-drawn character).
```

**Официальный, аналитический** (отчёт госоргану, исследование, совет директоров):
```
Muted sepia and steel-blue accent tones. Serious, solid, analytical report tone — NO cartoon
characters, NO mascots, NO jokes or playful decoration; diagrams must look precise and official,
like a state analytical briefing, not a casual social-media graphic.
```

## Разметка страницы (шаблон)

```
Aspect: 9:16 vertical.            ← инфографика, страница PDF, сторис
(или) Aspect: 16:9 horizontal.    ← слайд

Layout: <1–2 предложения: что нарисовано в центре — кольца, воронка, два циферблата со
стрелкой «разрыв», пирамида, дорога с шагами, карта регионов столбиками>.

Render this exact text, legibly, correct Russian Cyrillic spelling, nothing cropped, no other text:
TOP HEADLINE (large bold caps, two lines): "…"
SUBTITLE (one single line, do not repeat any words from the headline above): "…"
<подписи блоков, каждая со своим местом: LEFT gauge: "…", RIGHT gauge: "…", STEP 1: "…">
Below, italic handwritten-style script, the explanatory line: "…"
Footer, small printed text bottom: "<бренд или организация> · <дата>"
```

Пример страницы «разрыв» из аналитического отчёта (обезличен):
```
Layout: a wide "gap" comparison diagram — two hand-drawn circular gauges side by side,
connected by a horizontal double-headed arrow labeled "РАЗРЫВ" in the middle.
LEFT gauge, filled to 26%: big number "26%", label under it: "официальные каналы — сообщения в поддержку"
RIGHT gauge, filled to 58%: big number "58%", label under it: "жители — высказывания с критикой"
```

## Узбекский — две письменности

Строка про письменность заменяет «correct Russian Cyrillic spelling»:

- **Латиница:** `correct Uzbek Latin script (O‘zbek lotin yozuvi), use the letters oʻ gʻ with the
  modifier-letter apostrophe ʻ` — и в самом тексте писать `oʻ gʻ` через ʻ (U+02BB), твёрдый знак
  через ʼ (U+02BC): «Sunʼiy».
- **Кириллица:** `correct Uzbek Cyrillic script (Ўзбек кирилл ёзуви), with the letters ў қ ғ ҳ`.

Текст сначала вычитать навыком `humanizer-uz` (и `uzbek-editor`, если есть), потом в промпт.
Наружу — после вычитки носителем.

## Правила точности текста

- ≤ 6–8 текстовых блоков и ≤ 120–150 слов на картинку. Больше — модель путает и режет.
- Заголовок — капсом, 1–2 строки; длинные фразы дробить на подписи по 2–4 слова.
- «SUBTITLE … do not repeat any words from the headline» — иначе модель дублирует заголовок.
- Если подпись должна стоять один раз, так и писать: «each label appears only ONCE in the whole
  image» — у колец модель любит повторять подпись на нижней дуге.
- Латинские имена брендов писать латиницей в кавычках: «Claude», «Telegram» — иначе модель
  транслитерирует («Клод»).
- Ошибка в букве → сократить текст и перегенерировать. Поверх картинки текст не править:
  шрифт не совпадёт.
