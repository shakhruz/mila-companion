---
name: directors
description: "Директора хозяина через companion-api — список, файлы, диалоги, расход, правка через «да». Использовать при любом вопросе о его цифровых сотрудниках и в ритуалах утро/вечер."
---

# Директора хозяина (companion-api)

Я вижу только директоров своего хозяина — API отдаёт их по токену контейнера. Чужих нет.
Вызов — скрипт `api.sh` рядом с этим файлом (curl через unix-сокет; токен из env
`COMPANION_API_TOKEN`, сокет `COMPANION_API_SOCK`, по умолчанию `/run/companion/api.sock`).

```bash
S=.claude/skills/directors/api.sh
$S GET  /directors                                   # список: slug · клиент · тариф · жив ли · оплачено до
$S GET  "/directors/<slug>/files?path=AGENTS.md"     # AGENTS.md · USER.md · SOUL.md · STYLE.md · BRIEF.md
$S GET  "/directors/<slug>/files?path=memory/"       # список памяти; memory/<файл>.md — файл
$S GET  "/directors/<slug>/files?path=skills/INDEX.md"
$S GET  "/directors/<slug>/sessions?last=30"         # последние ходы с людьми (телефоны/карты скрыты)
$S GET  "/directors/<slug>/spend?days=7"             # расход по дням, топ моделей, остаток баланса
$S POST /directors/<slug>/propose '{"path":"AGENTS.md","why":"…","edits":[{"old":"…","new":"…"}]}'
$S POST /proposals/<id>/apply '{"card_id":"<card_id тапа>"}'   # ТОЛЬКО по тапу хозяина на карточке
$S POST /proposals/<id>/reject '{}'
$S GET  /proposals                                   # мои заявки и их состояние
```

## Правка директора — порядок
1. Улика: цитата из `sessions` или строка из файла — что именно не так.
2. `propose` с `edits` (точные `old`→`new`, old обязан встречаться ровно один раз) или `content`
   (весь файл). Ответ — `id` и `diff`.
3. Ответ `propose` несёт готовую карточку `card` (текст + кнопки «Применить»/«Нет», `allow` = его id).
   Кладу её файлом: `python3 -c 'import json,sys;json.dump(CARD, open("/home/companion/.claude/channels/telegram/outbox/card-<id>.json","w"))'`
   — sender отправит хозяину кнопки. Словами «да» в чате правка НЕ применяется.
4. Его тап приходит в чат как «[кнопка] Применить» с `card_id` в meta → `apply` с этим `card_id`.
   API сверяет тап по реестру карточек (кто нажал, какую кнопку); без тапа — 403, и это правильно.
   Тишина = нет. Заявка живёт сутки. Применение делает бэкап и сохраняет владельца файла — это API.
5. В `NOW.md`: «правка <slug>/<файл> предложена/принята».

## Что API не делает
Перезапуск, рождение, удаление, ключи, токены, деньги. Просьбу об этом хозяин передаёт
Миле Админ / кассе — я так и говорю, не обещаю.

## Ошибки
401/403 — «этого директора у меня нет» (не спорю, предлагаю проверить у Милы Админ).
Сокета нет — «связь с директорами сейчас недоступна, скажу, когда вернётся», без кухни наружу.
