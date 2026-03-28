# Atomic choice

## Elevator Pitch 
**«Что это?», «Для кого?», «В чём главная ценность?».**

«Атомный выбор» — это закрытая платформа для создания анонимных голосований и опросов, доступная исключительно студентам и сотрудникам НИЯУ МИФИ. Главная ценность — гарантированная честность и прозрачность волеизъявления внутри университетского сообщества благодаря верификации участников и независимости от внешних сервисов.

## Проблема и решение
*Проблема :*
Существующие опросы внутри университета не всегда отражают реальное мнение из-за возможности накрутки голосов, а ключевой внешний инструмент (Google Формы) может стать недоступным в любой момент.

*Решение:*
Мы создаем доверенную среду внутри периметра МИФИ. Платформа решает обе проблемы одновременно:
1.  **Верификация:** Доступ к голосованию только для подтвержденных пользователей (студентов/сотрудников), что исключает влияние извне.
2.  **Независимость:** Отечественный аналог Google Forms, работающий стабильно и доступный всегда.

## Целевая аудитория
*   Студенты НИЯУ МИФИ (всех курсов и направлений).
*   Сотрудники и преподаватели НИЯУ МИФИ.

## Ключевые преимущества
*   **Закрытость:** Участие только для верифицированных пользователей МИФИ (через корпоративную почту или иную интеграцию).
*   **Анонимность:** Гарантированная защита личности голосующего при сохранении честности подсчета голосов.
*   **Независимость:** Полноценный внутренний аналог зарубежных сервисов, безопасный с точки зрения санкционных рисков.

## Главные возможности
*   **Создание опросов:** Интуитивно понятный конструктор для создания голосований с различными типами ответов (один выбор, несколько, текст).
*   **Верификация участников:** Автоматическая проверка принадлежности пользователя к сообществу МИФИ при регистрации.
*   **Прозрачные результаты:** Отображение итогов голосования в понятной форме (графики, диаграммы) после завершения опроса.
*   **Анонимные ответы:** Техническая гарантия того, что ответ невозможно привязать к конкретному аккаунту.

## Технологии
*   **Фронтенд:** 
*   **Бэкенд:** 
*   **База данных:** 
*   **Аутентификация:** 

## Команда
*   **Костылева Анастасия (Product Leader):**
    *   *Основная роль:* 
    *   *Вклад в проект:*
*   **Татаринова Арина (Business Analyst):**
    *   *Основная роль:* 
    *  *Вклад в проект:*
*   **Красавина Софья (Designer):**
    *   *Основная роль:* 
    *  *Вклад в проект:*
*   **Невиницын Данила (Developer):**
    *   *Основная роль:* 
    *  *Вклад в проект:*
*   **Галюшин Ярослав (Developer):**
    *   *Основная роль:* 
    *  *Вклад в проект:*


# Atomic choice FastAPI — Локальный запуск

## Стек
- **Backend**: FastAPI + uvicorn
- **Blockchain**: Web3.py → Hardhat local node
- **Contracts**: Solidity (Whitelist, VotingFactory, VotingPoll, ZK stubs)
- **ZK**: Groth16 симуляция (VerifierStub принимает любой proof)
- **Frontend**: Jinja2 template + Vanilla JS SPA

## Структура

```
atomic-choice/
├── main.py                      # FastAPI app + lifespan
├── requirements.txt
├── deployments.json             # Auto-generated после деплоя
│
├── app/
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── blockchain.py        # Web3 connection + ABIs + send_tx()
│   │   ├── merkle.py            # Off-chain Merkle Tree (mirrors .sol)
│   │   └── zk.py               # ZK helpers: commitment, nullifier, stub proof
│   │
│   ├── models/
│   │   └── student.py           # In-memory student registry (8 seed students)
│   │
│   ├── schemas/
│   │   └── poll.py              # Pydantic request/response schemas
│   │
│   ├── services/
│   │   ├── deploy_service.py    # Deploys contracts from Hardhat artifacts
│   │   ├── whitelist_service.py # add_commitment() → on-chain + Merkle sync
│   │   └── poll_service.py      # createPoll() + castVote() → on-chain
│   │
│   └── routers/
│       ├── pages.py             # GET / → index.html
│       ├── polls.py             # GET /api/polls, POST /api/vote
│       ├── students.py          # GET /api/students
│       └── admin.py             # POST /api/admin/setup, /deploy, /whitelist
│
└── templates/
    └── index.html               # SPA (все страницы, нет зависимостей)
```

## Запуск

### Шаг 1 — Установить зависимости Python

```bash
cd atomic-choice
pip install -r requirements.txt
```

### Шаг 2 — Скомпилировать контракты

```bash
cd atomic-choice/contracts
npm install
npx hardhat compile
```

### Шаг 3 — Запустить Hardhat node

```bash
cd atomic-choice/contracts
npx hardhat node
```

Оставьте терминал открытым. В логах будете видеть все транзакции.

### Шаг 4 — Запустить FastAPI

```bash
cd atomic-choice
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### Шаг 5 — Открыть браузер

```
http://localhost:8000
```

Нажмите **"⚡ БЫСТРЫЙ СТАРТ"** в панели администратора — это автоматически:
1. Задеплоит все 4 контракта в Hardhat node
2. Добавит 8 студентов в вайтлист (8 транзакций)
3. Создаст 3 тестовых голосования (3 транзакции)

### Шаг 6 — Проголосовать

1. Нажать **"Войти"** → выбрать студента
2. Перейти в **"Голосования"** → открыть активный опрос
3. Выбрать вариант → **"ПРОГОЛОСОВАТЬ"**
4. Смотреть анимацию ZK-шагов + транзакцию в логах Hardhat

## API эндпоинты

```
GET  /api/polls                        — список голосований
GET  /api/polls/{address}             — детали + результаты
POST /api/vote                         — проголосовать
GET  /api/students                     — список студентов
GET  /api/merkle-proof/{wallet}        — Merkle inclusion proof

POST /api/admin/setup                  — деплой + вайтлист + опросы
POST /api/admin/deploy                 — только деплой
POST /api/admin/whitelist/{wallet}     — добавить одного студента
POST /api/admin/whitelist/batch/all   — добавить всех
POST /api/admin/polls/seed             — создать тестовые опросы
POST /api/admin/polls                  — создать произвольный опрос
GET  /api/admin/status                 — статус ноды и контрактов
```

## Как видеть транзакции в Hardhat node

В терминале с `npx hardhat node` вы увидите:

```
eth_sendRawTransaction
  Contract deployment: Whitelist
  Contract address: 0x5FbDB2315678afecb367f032d93F642f64180aa3
  From: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
  Value: 0 ETH
  Gas used: 1234567 of 5000000
  Block #2: 0xabc...

eth_sendRawTransaction
  Transaction: 0xdef...
  From: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
  To: 0x5FbDB2315678afecb367f032d93F642f64180aa3
  Gas used: 89432 of 107318
  Block #3: 0x123...
```

Каждый голос — отдельная транзакция `castVote()` с nullifier hash и ZK proof.
