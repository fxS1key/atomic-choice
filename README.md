# Atomic Choice

## Elevator Pitch
«Атомный выбор» — закрытая платформа для анонимных голосований и опросов, доступная исключительно студентам и сотрудникам НИЯУ МИФИ. Главная ценность — гарантированная честность и прозрачность волеизъявления внутри университетского сообщества благодаря верификации участников и независимости от внешних сервисов.

## Проблема и решение
**Проблема.** Существующие опросы внутри университета не всегда отражают реальное мнение из-за возможности накрутки голосов, а ключевой внешний инструмент (Google Forms) может стать недоступным в любой момент.

**Решение.** Доверенная среда внутри периметра МИФИ:
1. **Верификация:** голосовать могут только подтверждённые администратором участники.
2. **Анонимность:** ZK-proof + nullifier гарантируют «один человек — один голос» без раскрытия личности.
3. **Независимость:** работает на собственной инфраструктуре; без внешних API.

## Целевая аудитория
- Студенты НИЯУ МИФИ всех курсов и направлений.
- Сотрудники и преподаватели НИЯУ МИФИ.

## Ключевые возможности
- **Регистрация по паролю.** Никаких e-mail и SMS. Пара (ник, пароль) детерминированно превращается в приватный ключ Ethereum через scrypt-KDF. Сервер хранит только производный приватный ключ (для подписи демо-транзакций), пароль не сохраняется нигде.
- **Whitelist администратором.** Зарегистрированные участники появляются в админ-панели как «ожидают подтверждения»; админ одним кликом добавляет их в on-chain whitelist (Merkle-tree).
- **Создание опросов.** Любой одобренный участник может опубликовать опрос — он деплоится как смарт-контракт `VotingPoll`.
- **Анонимное голосование.** Голос подписывается приватным ключом пользователя, на блокчейн уходит через сервис-ретранслятор (на блокчейне нет привязки к нику). Проверка членства через Merkle inclusion proof, защита от повторного голосования через nullifier.
- **Скрытые промежуточные результаты.** Пока опрос активен, API возвращает нули — никакого «бандвагона». После завершения результаты публикуются.
- **Админ-токен.** Все эндпоинты `/api/admin/*` требуют заголовок `X-Admin-Token` (значение — в `admin_token.txt` либо переменной окружения `ADMIN_TOKEN`).
- **QR-код** для быстрой регистрации одногруппников через публичный туннель.

## Стек
- **Backend:** FastAPI + uvicorn
- **Blockchain:** Web3.py → Hardhat local node
- **Contracts:** Solidity (`Whitelist`, `VotingFactory`, `VotingPoll`, `VerifierStub`, `PoseidonStub`)
- **ZK:** Groth16 stub (production-замена — `snarkjs` в браузере)
- **Frontend:** Jinja2 + Vanilla JS SPA, `qrcode.js` для QR

## Структура проекта

```
atomic-choice/
├── main.py                            # FastAPI app + lifespan
├── requirements.txt
├── deployments.json                   # генерируется после деплоя
├── users.json                         # зарегистрированные участники (gitignored)
├── admin_token.txt                    # автогенерируемый токен админа (gitignored)
├── server_salt.bin / session_key.bin  # ключи сервера (gitignored)
│
├── app/
│   ├── core/
│   │   ├── auth.py                    # KDF: nick+password → eth pk, сессии, users.json
│   │   ├── admin_auth.py              # ADMIN_TOKEN + dependency для /api/admin/*
│   │   ├── config.py                  # Settings (.env)
│   │   ├── blockchain.py              # Web3 connection + ABIs + send_tx
│   │   ├── keys.py                    # резервные 10 keypair'ов (legacy demo)
│   │   ├── merkle.py                  # Off-chain Merkle Tree
│   │   └── zk.py                      # ZK helpers: commitment, nullifier, stub proof
│   │
│   ├── models/
│   │   └── student.py                 # Реестр участников (seed + keypair + registered)
│   │
│   ├── schemas/
│   │   └── poll.py                    # Pydantic-схемы
│   │
│   ├── services/
│   │   ├── deploy_service.py
│   │   ├── whitelist_service.py       # глобальный on-chain whitelist
│   │   ├── poll_whitelist_service.py  # per-poll whitelist
│   │   ├── poll_service.py            # createPoll + castVote
│   │   └── user_service.py            # связка users.json ↔ Student-реестр
│   │
│   └── routers/
│       ├── pages.py                   # / , /how-it-works , /legacy
│       ├── auth.py                    # /api/auth/{register,login,logout,me}
│       ├── polls.py                   # /api/polls + /api/vote
│       ├── students.py
│       └── admin.py                   # /api/admin/* (под X-Admin-Token)
│
├── templates/
│   ├── app.html                       # SPA-оболочка
│   └── how_it_works.html              # объяснение криптографии
│
├── static/
│   ├── app.js                         # вся SPA-логика
│   ├── style.css / app.css
│   ├── logo.png
│   └── atomic_choice.html             # legacy-UI, доступен по /legacy
│
├── contracts/                         # Hardhat-проект (Solidity)
│   ├── contracts/                     # *.sol
│   ├── scripts/
│   └── hardhat.config.cjs
│
└── docs/
    ├── User Stories.md
    ├── Use Case «Создание голосования».md
    ├── Use Case «Участие в опросе».md
    └── ...
```

## Запуск локально

### 1. Зависимости Python
```bash
cd atomic-choice
pip install -r requirements.txt
```

### 2. Скомпилировать контракты
```bash
cd contracts
npm install --save-dev hardhat@^2.22.0 @nomicfoundation/hardhat-toolbox@^5.0.0 --legacy-peer-deps
npx hardhat compile
```

### 3. Запустить Hardhat-ноду
```bash
cd contracts
npx hardhat node
```
Оставьте терминал открытым: вы будете видеть все транзакции.

### 4. Запустить FastAPI
```bash
cd atomic-choice
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

При первом запуске в корне появятся `admin_token.txt` (токен админа) и `server_salt.bin`. **Не коммитьте их в Git** — они уже в `.gitignore`.

### 5. Открыть браузер
```
http://localhost:8000
```

В навигации:
- **Главная** — статистика и активные опросы.
- **Голосования** — все опросы с фильтрами.
- **Создать** — форма создания опроса (требует одобрения).
- **Как это работает** — пошаговое объяснение криптографии.
- **Админ** — панель администратора (требует токена из `admin_token.txt`).

### 6. Демо-сценарий для презентации

1. Запустите Hardhat-ноду и FastAPI.
2. Откройте `http://localhost:8000`, перейдите в **Админ**, введите токен из `admin_token.txt`.
3. Нажмите **«⚡ Быстрый старт»** — задеплоит контракты, добавит resервные keypair'ы, создаст 3 тестовых опроса.
4. Раздайте одногруппникам публичный URL (через Cloudflare Tunnel — см. ниже). Они увидят QR-код в админке у вас.
5. Каждый одногруппник вводит **ник + пароль**, регистрируется. В админке вы видите их в разделе **«🆕 Ожидают подтверждения»**.
6. Кликаете **«✓ В вайтлист»** для каждого — пользователь получает уведомление и может голосовать.
7. Создаёте/выбираете опрос → пользователи голосуют → результаты раскрываются после `endTime`.

## Публичный хостинг с ноутбука (бесплатно)

Самый простой способ — Cloudflare Tunnel:

```bash
# Один раз: скачать cloudflared
# https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

# Запустить туннель прямо к вашему localhost:8000
cloudflared tunnel --url http://localhost:8000
```

Cloudflare выдаст HTTPS-URL вида `https://xxx-yyy-zzz.trycloudflare.com`. Положите его в `.env`:

```env
PUBLIC_URL=https://xxx-yyy-zzz.trycloudflare.com
ADMIN_TOKEN=любая-длинная-строка
```

После рестарта FastAPI этот URL будет в QR-коде на админ-панели. Альтернативы: `ngrok`, `localtunnel`.

## API эндпоинты

```
# Аутентификация пользователей
POST /api/auth/register          { nick, password }
POST /api/auth/login             { nick, password }
POST /api/auth/logout
GET  /api/auth/me                → текущий пользователь

# Голосования
GET  /api/polls
GET  /api/polls/{addr}
GET  /api/polls/{addr}/results   → 403, пока опрос активен
POST /api/polls                  → создать опрос (требует сессии)
POST /api/vote                   → проголосовать (требует сессии)
GET  /api/polls/{addr}/whitelist
POST /api/polls/{addr}/whitelist → per-poll whitelist (создатель)
GET  /api/merkle-proof/{wallet}

# Студенты / участники
GET  /api/students

# Админ (требует заголовка X-Admin-Token)
GET  /api/admin/status
POST /api/admin/setup                  → деплой + seed
POST /api/admin/deploy
GET  /api/admin/users/pending
GET  /api/admin/users/approved
POST /api/admin/users/{wallet}/approve → одобрить регистрацию
POST /api/admin/whitelist/{wallet}
POST /api/admin/sync
```

## Криптография в двух словах

```
ник + пароль
   │
   ▼  scrypt(password, salt = server_salt || nick)
private_key (32 байта)
   │
   ▼  sha256
secret  ∈ field
   │
   ▼  Poseidon
commitment  ───►  Whitelist.addCommitment(...)  on-chain
                              │
                              ▼ Merkle root
                          updates VotingPoll.validRoots

Голос:
   secret + poll_id  ──Poseidon──►  nullifier  ───►  VotingPoll.castVote(...)
       (никогда не выходит за пределы сервера в demo)
```

Подробное объяснение — на странице `/how-it-works`.

## Покрытие User Stories

| Story | Реализация |
|---|---|
| US1 (участие) | `/`, `/api/vote`, `app.js → doVote` |
| US2 (анонимность) | nullifier + relay-tx + `results_hidden` |
| US3 (создание опроса) | `POST /api/polls`, страница «Создать» |
| US4 (верификация) | админ-одобрение через `POST /api/admin/users/{wallet}/approve` |
| US5 (анти-двойник) | nullifier (`poll_service.cast_vote`) |

## Команда
- **Костылева Анастасия** — Product Leader
- **Татаринова Арина** — Business Analyst
- **Красавина Софья** — Designer
- **Невиницын Данила** — Developer
- **Галюшин Ярослав** — Developer

## Лицензия
См. `LICENSE`.
