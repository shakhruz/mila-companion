---
name: "humanizer-uz"
description: "Переписать любой узбекский текст с канцелярита на живой человеческий язык — камертон Абдуллы Кадыри, Абдуллы Каххара и Абдуллы Арипова. Использовать при ЛЮБОМ uz-тексте, который прочитает человек: посты и новости, welcome-сообщения ботов, объяснение законов и ПКМ простыми словами, перевод ТЗ/консалтинга/договоров в понятный вид, ответы клиентам, лендинги. Даёт правила синтаксиса, словарь замен «канцелярит → живое» и тест «прочитай вслух». Орфографию проверяет соседний скилл uzbek-editor; наружный текст перед публикацией вычитывает носитель."
---
# Humanizer-UZ — живой узбекский вместо канцелярита

Задача скилла одна: **лаконично выразить суть правильным построением предложения — так, чтобы глаз не спотыкался и было видно, что писал человек, а не робот.**

Скилл не «украшает» текст. Он вынимает из бюрократической обёртки то, что там сказано, и говорит это по-узбекски так, как говорят люди.

---

## 1. Камертон: три Абдуллы

Три автора — эталон живого литературного узбекского, понятного массовому читателю. Когда сомневаешься «так пишет человек или машина» — спроси: сказал бы так Каххар?

| Автор | Годы | Чему учит |
|---|---|---|
| **Abdulla Qodiriy** (Абдулла Кадыри) | 1894–1938 | Живой повествовательный ритм, конкретный портрет вместо характеристики, диалог как двигатель. Отец узбекского романа. **Общественное достояние.** |
| **Abdulla Qahhor** (Абдулла Каххар) | 1907–1968 | Экономия: одно предложение — одна мысль, глагол-удар в конце, пословица вместо абзаца рассуждений. Прямой враг канцелярита — высмеял его в фельетоне «Nutq». **Права под охраной.** |
| **Abdulla Oripov** (Абдулла Арипов) | 1941–2016 | Точное имя чувства вместо абстракции, ритм и параллелизм, риторический вопрос как способ позвать читателя. **Права под охраной.** |

**Граница цитирования.** Библиотека текстов (см. §7) — внутренняя, для анализа стиля. Кадыри цитируем свободно. Каххара и Арипова — только 1–2 короткие строки как иллюстрация приёма, внутри наших рабочих материалов; целиком их тексты наружу не публикуем и в клиентские материалы не вставляем.

**Готовый анти-эталон.** Фельетон Каххара «Nutq» — оратор поздравляет жену с годовщиной свадьбы языком доклада: `«Bugungi kunda choynagimiz qopqoqqa ega emas, mutlaqo ega emas»` — вместо «choynakning qopqogʻi yoʻq». Это ровно то, что мы вычищаем. Файл: `library/uz-classics/qahhor/nutq-fel-eton.txt`.

---

## 2. ПРОЦЕСС гуманизации (пять шагов, по порядку)

### Шаг 1. Прочитал целиком
Не начинай переписывать с первой фразы. Прочитай весь абзац/документ и ответь себе на три вопроса:
- **Кто действует?** (в канцелярите деятель спрятан или его нет)
- **Что он делает?** (действие спрятано в отглагольном имени: `amalga oshirish`, `taʼminlash`)
- **Что от читателя требуется / что ему меняется?**

Если на эти вопросы ответа в тексте нет — гуманизация не поможет, нужен факт от заказчика. Не выдумывать.

### Шаг 2. Вычленил суть
Выпиши суть **одной фразой на 5–9 слов**, как заголовок. Это ядро. Всё остальное — детали вокруг него.
Пример: абзац на 60 слов о порядке подачи документов = `Ruxsat olish uchun hujjatlarni toʻliq yigʻib bering.`

Всё, что не работает на ядро (`bevosita`, `tegishli`, `belgilangan tartibda`, `shuni taʼkidlab oʻtish kerakki`) — вон. Проверка: убрал слово, смысл не изменился → слово было мусором.

### Шаг 3. Пересобрал по правилам синтаксиса (§3)
Строишь заново, не правишь по кускам. Канцеляритную фразу нельзя «подлатать» — её надо сказать заново своими словами.

### Шаг 4. Заменил канцелярит по словарю (§4)
Проход по словарю замен. Обязательный технический прогон — поиск маркеров:

```
amalga oshir | taʼminla | mazkur | ushbu | mavjud | ega emas | hisoblanadi
taqdim et | yuzasidan | munosabat bilan | tomonidan | belgilangan tartibda
taʼkidlab oʻtish | lozim topildi | bevosita | joriy etil | imkoniyat yaratildi
```
**Источник в кириллице** (lex.uz отдаёт акты именно так) — латинские маркеры по нему не ищутся. Кириллический прогон:
```
амалга ошир | таъминла | мазкур | ушбу | мавжуд | эга эмас | ҳисобланади
тақдим эт | юзасидан | муносабат билан | томонидан | белгиланган тартибда
таъкидлаб ўтиш | лозим | бевосита | жорий этил | имконият яратилди
белгилансин | тасдиқлансин | зиммасига юклансин | амалга оширилади
```
Формы на `-син` (`тасдиқлансин`, `белгилансин`, `таъминласин`) — приказная форма НПА; в пересказе для человека они становятся прошедшим временем факта (`tasdiqlandi`) или настоящим правилом (`beriladi`), но **только там, где акт уже действует** — иначе получится, что поручение выполнено.

Каждое найденное — либо заменено, либо выброшено, либо (редко) осознанно оставлено, потому что это юридический термин, который нельзя менять.

### Шаг 5. Проверка «прочитай вслух»
Финальный гейт, восемь вопросов:
1. **Дыхание.** Каждую фразу можно произнести вслух на одном дыхании? Нет → режь. Ориентир: больше 20 слов — почти всегда две мысли в одной фразе.
2. **Спотыкание.** Есть место, где глаз возвращается назад перечитать? Значит, новое стоит не там: известное — в начало, новое — перед сказуемым.
3. **Робот.** Есть ли `amalga oshiriladi / hisoblanadi / ega emas`? Значит, робот ещё виден.
4. **Ритм.** Все предложения одинаковой длины? Добавь короткий удар в 2–4 слова после длинного.
5. **Кто говорит.** Понятно, кто действует и к кому обращаются (`siz`, а не `foydalanuvchilar tomonidan`)?
6. **Факты целы.** Суммы, сроки, названия, номера документов — не потерялись и не «округлились»? Гуманизация меняет форму, не содержание.
7. **Обратная сверка (для нормативки — обязательна).** Идёшь по ПОСЛЕ фраза за фразой и для каждой показываешь пальцем место в ДО. Не нашёл — вычёркиваешь. Живой случай: «размещение по личному обращению человека» превратилось в бодрое `Uni hech kim olib kelmaydi` («его никто не приводит») — красиво, по-человечески и в акте этого нет. **Контрабанда лезет не в фактах, а в связках:** отрицания («никто не», «без …ни разу»), выводы («значит», «то есть»), обещания («обязательно», «гарантированно»), инверсия условия (акт: «размещают на основании заключения» → пересказ: «есть заключение — примут», а это уже обещание приёма). Простая суть — не то же самое, что простой вывод из сути.
8. **Обрыв фрагмента.** Работаешь с куском, а не целым актом? Незаконченную фразу НЕ дописывать по смыслу — обрезать на последней целой мысли и сказать вслух, где обрезано.

---

## 3. Правила живого узбекского синтаксиса

Выведены из: Qodiriy — «Oʻtkan kunlar», «Uloqda»; Qahhor — «Bemor», «Oʻgʻri», «Anor».

1. **Одно предложение — одно событие, глаголы каскадом.**
   ✔ `Tabib qon oldi… baxshi oʻqidi. Tovuq soʻyib qonladi.` (Bemor)
   ✘ `Tabib tomonidan qon olish amalga oshirildi.`

2. **Личная форма глагола вместо отглагольного имени.** Каждое `…ni taʼminlash maqsadida` переписывается в `…sin deb` / `…uchun` + настоящий глагол.
   ✔ `savat toʻqiydi` ✘ `savat toʻqish faoliyatini olib boradi`

3. **Пассив и безличность — это голос чиновника, классики им маркируют бездушие.** В «Oʻgʻri» амин говорит: `Nega yigʻlanadi? Yigʻlanmasin!.. arz qilinsin-da!` Человек пишет активным залогом с живым субъектом.
   ✔ `hujjatni olib keling` ✘ `hujjat taqdim etilishi lozim`

4. **Начинай с конкретного деятеля, не с рамки.**
   ✔ `Sotiboldining xotini ogʻrib qoldi.` — первая фраза рассказа, суть сразу.
   ✘ `Maʼlumki, aholi salomatligi masalasi dolzarb boʻlib turibdi.`

5. **Ритм: длинное — короткое.** После развёрнутой фразы — удар в 2–4 слова: `Hammayoq jim.` · `Gʻovur bosildi.` Канцелярит держит все предложения одной длины, и глаз спотыкается именно об это.

6. **Связки — деепричастие на `-ib` и частица `-da`, не именные обороты.**
   ✔ `Choyni naridan-beri ichib, otxonaga yugurdim.` (Uloqda)
   ✘ `Yuqorida qayd etilganlardan kelib chiqqan holda`, `shu munosabat bilan`
   Цепочка деепричастий — максимум две, дальше точка.

7. **Известное — в начало, новое — под ударение перед сказуемым.** Абзац течёт подхватом темы: `Shaharda bitta doktorxona bor. Bu doktorxona toʻgʻrisida Sotiboldining bilgani shu: …` — а не списком несвязанных пунктов.

8. **Обобщение — пословицей или предметным образом, не абстракцией.** `Yoʻgʻon choʻziladi, ingichka uziladi` · `Quruq qoshiq ogʻiz yirtadi`. Вместо `moliyaviy yuk ortadi` — образ, который читатель видит. **Не больше одной пословицы на текст.**

9. **Абзац = тезис → 2–4 конкретики → короткий вывод.** Открытие «Bemor»: беда → перечень лечений → `Bularning hammasi pul bilan boʻladi.` Схема переносится на любой документ.

10. **Настоящее время для живой картины и для инструкций.**
    ✔ `tugmani bosasiz — roʻyxat chiqadi` ✘ `bosilgandan soʻng chiqarilishi kuzatiladi`

11. **Определения — конкретные прилагательные перед словом, а не придаточные с `boʻlgan / hisoblangan`.**
    ✔ `tajribali mutaxassis` ✘ `yuqori malakaga ega boʻlgan hisoblangan mutaxassis`
    Кадыри: `uzun boʻylik, qora choʻtir yuzlik, chagʻir koʻzlik… bir kishi edi.`

12. **Частицы `-da, -ku, -chi, axir, shekilli` — смазка доверия.** `Bir nima berish lozim-da.` · `Axir, nima qilay?` Канцелярит стерилен без них. Норма — 1–2 частицы на абзац, не больше: пересол читается как фальшивая простота.

**Сквозной принцип.** У Кадыри и Каххара предложение несёт ровно одну мысль, глагол стоит в конце как удар, а связность даётся подхватом темы и деепричастиями — не словами-скрепами `mazkur, ushbu munosabat bilan, oʻz navbatida`.

---

## 4. Словарь замен: канцелярит → живое

| # | Канцелярит | Живое |
|---|---|---|
| 1 | `amalga oshirish` | назвать само действие: `qurdi, ochdi, boshladi, qildi` |
| 2 | `mazkur / ushbu` | `bu, shu` |
| 3 | `mavjud` / `mavjud emas` | `bor` / `yoʻq` |
| 4 | `…ga ega / ega emas` | `-li` или `bor` / `yoʻq` (`choynakning qopqogʻi yoʻq`) |
| 5 | `talab etiladi / zarur hisoblanadi` | `kerak` |
| 6 | `hisoblanadi` | `-dir` или ничего: `U shifokor.` |
| 7 | `taqdim etmoq` | `bermoq, topshirmoq, koʻrsatmoq` |
| 8 | `taʼminlamoq` | `bermoq, yetkazmoq` |
| 9 | `bartaraf etmoq / barham bermoq` | `tuzatmoq, yoʻqotmoq, toʻxtatmoq` |
| 10 | `foydalanuvchi tomonidan …-ladi` | активный залог: кто делает — тот и подлежащее |
| 11 | `maqsadida` | `uchun`, `deb` (`pul topaman deb`) |
| 12 | `yuzasidan / xususida` | `haqida, toʻgʻrisida` |
| 13 | `shu munosabat bilan` | `shuning uchun, shunga koʻra` |
| 14 | `muhokama qilish yoʻli bilan` | `gaplashib, kengashib` |
| 15 | `qaror qabul qilindi` | `…ga kelishdi`, `…deb qaror qilishdi` (с живым субъектом) |
| 16 | `faoliyat yuritadi / olib boradi` | `ishlaydi, qiladi` |
| 17 | `oʻz ichiga oladi` | `…bor`, `…kiradi` |
| 18 | `natijasida` | `-gani uchun` или деепричастие `-ib` |
| 19 | `joriy etildi` | `kiritildi, boshlandi, ishga tushdi` |
| 20 | `taʼkidlab oʻtish kerakki / shuni aytish lozimki` | выбросить, сказать суть |
| 21 | `bevosita, tegishli, belgilangan tartibda` | в 90% случаев выбросить без потери смысла |
| 22 | `imkoniyat yaratildi` | `endi …sa boʻladi`, `…mumkin` |
| 23 | `yosh avlod vakillari` | `yoshlar, bolalar` |
| 24 | `aholi punkti` | конкретное имя: `shahar, qishloq, mahalla`, `Toshkent`, `Margʻilon` |
| 25 | `mablagʻ ajratildi` | `pul berildi` + конкретная сумма |

### Лексические правила
1. **Глагол — царь предложения.** У действия должен быть собственный глагол, и он стоит близко к началу мысли: `Sotiboldining xotini ogʻrib qoldi` — 4 слова, вся экспозиция.
2. **Четыре живых сказуемых закрывают половину канцелярита:** `bor · yoʻq · kerak · mumkin`.
3. **Активный залог, субъект — человек.** Даже учреждение действует через человека: `amin kuldi`, `ellikboshi kirdi`.
4. **Считай конкретно.** У Каххара всегда `18 tanga`, `uch soʻm`, `bir qop somon` — не `maʼlum miqdordagi mablagʻ`.
5. **Тёплое обращение:** `siz`, `aziz oʻquvchi`, `bolam`, `otaxon`, `onajon`. Не `fuqarolar`, не `foydalanuvchilar`.
6. **Урок Арипова для прозы:** конкретное имя чувства вместо абстракции (`orzu, armon, gʻussa, hayrat, mehr`); риторический вопрос (`Nechun? Nahot?`) как способ позвать читателя; параллелизм — три однотипные короткие строки читаются легче, чем список через `hamda … hamda`.

---

## 5. ДО / ПОСЛЕ

### Пара 1 — лексузовский абзац (порядок выдачи разрешения)

**ДО (канцелярит):**
> Mazkur Nizom talablariga muvofiq, tadbirkorlik subyektlari tomonidan faoliyatni amalga oshirish uchun ruxsat berish tartib-taomili doirasida taqdim etiladigan hujjatlar roʻyxati belgilangan tartibda tasdiqlanadi hamda ularning toʻliqligini taʼminlash yuridik shaxs zimmasiga yuklatiladi. Shuni taʼkidlab oʻtish kerakki, hujjatlar toʻliq boʻlmagan taqdirda ariza koʻrib chiqilmasdan qaytarilishi mumkin.

**ПОСЛЕ (живое):**
> Ishni boshlash uchun ruxsat kerak. Qanday hujjatlar kerakligi roʻyxatda yozilgan — roʻyxat quyida. Hujjatlarni toʻliq yigʻib berish sizning ishingiz. Bitta qogʻoz yetishmasa, arizani koʻrib ham oʻtirishmaydi, qaytarib berishadi.

*Что сделано:* `mazkur` → выброшено · `tomonidan … amalga oshirish` → `ishni boshlash` · `taqdim etiladigan hujjatlar roʻyxati … tasdiqlanadi` → `roʻyxatda yozilgan` · `taʼminlash zimmasiga yuklatiladi` → `sizning ishingiz` · `shuni taʼkidlab oʻtish kerakki` → выброшено · длинная фраза разбита на четыре, последняя — с бытовым образом (`bitta qogʻoz yetishmasa`).
*Граница:* если это пересказ нормативного акта — рядом ставим ссылку на оригинал и оговорку, что юридическую силу имеет текст акта.

### Пара 2 — ТЗ / консалтинг

**ДО:**
> Loyihaning maqsadi mijozlar bilan ishlash jarayonlarini optimallashtirish orqali xizmat koʻrsatish sifatini oshirishni taʼminlashdan iborat boʻlib, ushbu maqsadga erishish uchun mavjud biznes-jarayonlar tahlil qilinishi hamda avtomatlashtirish imkoniyatlari aniqlanishi lozim hisoblanadi.

**ПОСЛЕ:**
> Maqsad bitta: mijoz javobni tez olsin. Buning uchun avval ish hozir qanday ketayotganini kuzatamiz — kim nima qiladi, vaqt qayerda yoʻqoladi. Keyin qaysi qadamni mashina bajara oladi, oʻshani ajratamiz.

*Что сделано:* цель названа человеческим результатом, а не `sifatini oshirishni taʼminlash` · `mavjud biznes-jarayonlar tahlil qilinishi lozim` → `kuzatamiz`, деятель — мы · тире вместо `hamda` · три шага стоят по порядку времени (`avval … keyin`).

### Пара 3 — welcome-сообщение бота

**ДО:**
> Hurmatli foydalanuvchi! Sizga taqdim etilayotgan mazkur bot orqali shahar boʻyicha dolzarb maʼlumotlarni olish imkoniyati yaratilgan boʻlib, undan foydalanish uchun tegishli boʻlimni tanlashingiz talab etiladi.

**ПОСЛЕ:**
> Assalomu alaykum! Men Mila — shahar boʻyicha yordamchingizman. Ob-havo, yangiliklar, yaqin-atrofdagi joylar: nimasi kerak boʻlsa, soʻrang. Pastdagi tugmani bosing yoki shunchaki yozib yuboring.

*Что сделано:* появился говорящий (`Men Mila`) и адресат на `siz` · `imkoniyat yaratilgan` → перечень конкретных вещей · `talab etiladi` → `bosing`, `yozib yuboring` · ритм: длинная строка — короткая.

---

## 6. Границы и связки

**Что скилл НЕ делает:**
- Не меняет факты, суммы, сроки, номера актов, названия органов и имена собственные. Форма — наша, содержание — заказчика.
- Не заменяет юридический текст. Пересказ закона — это пересказ: ссылка на первоисточник и оговорка обязательны (юридическую силу имеет оригинал). Готовая концовка, ставится всегда:
  `Bu — qaror mazmunini oddiy til bilan aytib berish. Yuridik kuchga ega matn — <organ>ning <sana>dagi <raqam>-son qarori, lex.uz.`
- Термин-определение из акта (`muayyan yashash joyiga ega boʻlmagan shaxs`, `maʼmuriy reglament`) в теле пересказа оставляем дословно и в кавычках — заголовок и объяснение вокруг него могут быть бытовыми (`uyi yoʻq odam`), сам термин подменять нельзя: по нему человек найдёт себя в документе.
- Не выдумывает недостающее. Не понял, кто действует, — спросил, а не додумал.
- Не «упрощает» термин, у которого нет бытового эквивалента (`litsenziya`, `deklaratsiya`). Термин оставляем, объясняем рядом одной фразой.

**Орфография — соседний скилл `uzbek-editor`.** Он держит апострофы (ʻ U+02BB в `oʻ/gʻ`, ʼ U+02BC в `sanʼat`), латиницу-2021, соответствия кириллица↔латиница и чек-лист перевода ru→uz без калек. Порядок работы: **сначала humanizer-uz (что и как сказано) → потом uzbek-editor (как написано)**. Смешение вариантов апострофа в одном документе — брак, это ловит редактор.

**Носитель.** Любой узбекский текст, уходящий наружу (клиенту, в канал, на сайт, в бота), после двух скиллов вычитывает наш редактор-носитель. Скилл поднимает качество черновика — он не отменяет живого человека.

**Графика.** Кириллица или латиница — по аудитории канала, не по вкусу. В одном тексте — одна графика.

---

## 7. Библиотека для дообучения

внутренний конспект (в шаблон не входит) — каталог в `INDEX.md` (произведение · год · источник-URL · формат · полнота). Внутренняя, для анализа стиля.

**Чистый текст без OCR-шума — лучшие образцы:**
- `qodiriy/otkan-kunlar.txt`, `qodiriy/mehrobdan-chayon.txt` — повествование, портрет, диалог
- `qodiriy/uloqda.txt`, `qodiriy/tinch-ish.txt`, `qodiriy/jinlar-bazmi.txt` — короткая проза
- `qahhor/bemor-hikoya.txt`, `qahhor/o-g-ri-hikoya.txt`, `qahhor/anor-hikoya.txt` — эталон экономии
- `qahhor/nutq-fel-eton.txt`, `qahhor/hiqichoq-feleton.txt`, `qahhor/bizning-mulohazalarimiz-feleton.txt` — **анти-эталон: канцелярит глазами Каххара**
- `qahhor/adabiyot-muallimi-hikoya.txt` — речь «умного» персонажа, который говорит пусто
- `oripov/sherlar-saylanma-ziyouz-lat.txt`, `oripov/ona-tili-1965-lat.txt` — ритм, параллелизм, имена чувств

Файлы с `-ocr` в имени — сканы со средним качеством распознавания, для сверки стиля годятся, для цитат — нет.

**Как дообучаться:** перед большой uz-задачей прочитай один короткий рассказ Каххара целиком (7–10 тыс. знаков — 3 минуты) и один фельетон. После этого канцелярит в чужом тексте видно физически.
