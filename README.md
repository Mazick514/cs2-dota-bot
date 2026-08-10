# CS2 + Dota 2 Teams Bot

Один Telegram-бот для отслеживания профессиональных команд **CS2** и **Dota 2** в одних и тех же группах. Используется единственный `BOT_TOKEN`.

В каждой Telegram-группе хранятся независимые списки по игре. Например, отслеживание `NAVI` в CS2 и `Team Spirit` в Dota 2 не пересекаются даже при совпадении provider ID: связь хранится с `chat_id`, `team_id` и `game`.

## Источник esports-данных

Используется PandaScore, без scraping HLTV или Liquipedia. Один `PANDASCORE_API_KEY` применяется и для CS2, и для Dota 2.

- CS2: `GET /csgo/teams`, `GET /csgo/matches/past`.
- Dota 2: `GET /dota2/teams`, `GET /dota2/matches/past`.

Для подробного результата бот дополнительно и только в режиме best-effort использует документированные endpoint'ы PandaScore:

- CS2: `GET /csgo/matches/{match_id}/players/stats` и `GET /csgo/matches/{match_id}/games`;
- Dota 2: `GET /dota2/matches/{match_id}/players/stats` и `GET /dota2/matches/{match_id}/games`.

Оба набора подробных данных требуют тариф PandaScore Historical или Real-time. Для них используется тот же единственный `PANDASCORE_API_KEY`; второй Telegram-бот и второй `BOT_TOKEN` не создаются.

PandaScore документирует оба Dota 2 endpoint как доступные на всех планах; конкретный ключ всё равно должен иметь доступ к выбранному тарифу. См. [Dota 2 teams](https://developers.pandascore.co/reference/get_dota2_teams), [Dota 2 past matches](https://developers.pandascore.co/reference/get_dota2_matches_past), [Dota 2 plan reference](https://developers.pandascore.co/docs/plan-reference) и [filtering/search](https://developers.pandascore.co/docs/filtering-and-sorting).

## Архитектура

```text
Telegram handlers
    → services
    → repositories / provider interface
    → PandaScore CS2 or Dota 2 provider
```

`PandaScoreGameProvider` содержит общий HTTP/parsing-код, а `PandaScoreCS2Provider` и `PandaScoreDota2Provider` задают только игру и официальный API-prefix. `MatchTracker` опрашивает оба provider одновременно, но отправляет результат только в те группы, где отслеживается соответствующая команда и игра.

Дедупликация общая: `sent_notifications` имеет уникальный ключ `(chat_id, match_id, notification_type)`. Матчи в базе также разделены по `game`.

## Уведомления о матчах

После завершения матча бот всегда отправляет короткое текстовое сообщение с командой, соперником, исходом, счётом серии и турниром. Если PandaScore вернул подробную статистику, сразу после текста отправляется собственный PNG scoreboard (ширина 1600 px, адаптивная высота), сформированный `ScoreboardRenderer`.

- CS2: результат каждой карты, K/D/A, KAST, ADR, Rating и доступные дополнительные показатели (HS, FKΔ, flash assists, clutch, multi/utility kills).
- Dota 2: результат каждой игры, K/D/A, GPM, XPM, сыгранные герои и доступные дополнительные показатели (LH, denies, hero/tower damage, KP, wards).

`ScoreboardRenderer` получает только нормализованные domain-модели: он не делает HTTP-запросов, не снимает скриншоты и не парсит HLTV/Liquipedia. При недостаточном тарифе, ответе API без статистики, ошибке рендеринга или отправки картинки текстовый результат остаётся доставленным, а причина пишется в лог.

## Установка и запуск (Windows PowerShell)

Требуется Python **3.14.6**.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполните `.env`:

```dotenv
BOT_TOKEN=123456:replace_with_telegram_token
PANDASCORE_API_KEY=replace_with_pandascore_token
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
MATCH_POLL_INTERVAL_SECONDS=60
LOG_LEVEL=INFO
```

Старое имя `CS2_API_KEY` также поддерживается как обратная совместимость, но для новой конфигурации используйте только `PANDASCORE_API_KEY`.

Создайте бота через [@BotFather](https://t.me/BotFather): команда `/newbot` выдаст единственный `BOT_TOKEN`. Добавьте этого бота в нужную группу и выдайте ему права администратора, чтобы он мог проверять права пользователей через Telegram Bot API.

```powershell
python -m app.main
```

## Telegram-команды

CS2:

```text
/csaddteam NAVI
/csaddteam
/csremoveteam NAVI
/csremoveteam
/csteams
/cshelp
/cssettings
```

Dota 2:

```text
/dotaaddteam Spirit
/dotaaddteam
/dotaremoveteam Spirit
/dotaremoveteam
/dotateams
/dotahelp
/dotasettings
```

`/csaddteam`, `/csremoveteam`, `/cssettings`, `/dotaaddteam`, `/dotaremoveteam` и `/dotasettings` доступны только администраторам группы. Команды списков и справки доступны всем. Добавление команды выполняется после выбора/подтверждения inline-кнопкой.

## Проверки

```powershell
pip install -r requirements-dev.txt
python -m compileall app tests
ruff check .
mypy app
pytest
```

Тесты проверяют CS2 и Dota 2 provider parsing, нормализацию map/game/player статистики, создание PNG, порядок «текст → картинка», безопасный fallback без картинки, разделение списков для разных игр в одной группе, обработку обеих игр одним tracker, дедупликацию, права, ошибки provider и обратную совместимость `CS2_API_KEY`.

## Docker и Koyeb

```powershell
docker build -t esports-teams-bot .
docker run --env-file .env --name esports-teams-bot esports-teams-bot
```

Для Koyeb загрузите проект в GitHub, создайте Service из репозитория, выберите builder `Dockerfile` и тип `Worker`. В настройках добавьте `BOT_TOKEN`, `PANDASCORE_API_KEY`, `DATABASE_URL`, `MATCH_POLL_INTERVAL_SECONDS` и `LOG_LEVEL` как environment variables. Для постоянной работы используйте PostgreSQL:

```text
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE
```

Koyeb поддерживает GitHub deployment с Dockerfile и автоматический redeploy при push. См. [официальную инструкцию Koyeb](https://www.koyeb.com/docs/build-and-deploy/deploy-with-git).
