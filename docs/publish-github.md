# Как загрузить проект на GitHub

Архив содержит один проект `orders-data-lab`. Распакуйте его и откройте папку, где лежит `pyproject.toml`. Команды одинаковы для PowerShell и терминала Linux.

## 1. Проверить проект локально

Создайте окружение и установите зависимости по README. В Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m orders_lab demo
```

## 2. Создать репозиторий

На [GitHub](https://github.com/new) создайте репозиторий:

- Repository name: `orders-data-lab`.
- Description: `Учебный проект: FastAPI API заказов, ETL и SQL-аналитика продаж`.
- Public — если хотите показывать его в портфолио; Private — если пока изучаете.
- Оставьте добавление README, `.gitignore` и лицензии выключенным: файлы проекта уже подготовлены, выбор лицензии можно сделать позже.

## 3. Сделать первый коммит

В терминале **в корне проекта**:

```bash
git init
git add .
git status
git commit -m "Add orders API, data pipeline and sales analytics"
git branch -M main
```

В `git status` должны быть исходники, тесты, документация и `docs/demo-report`. Папки `.venv`, `data`, `reports` и файл `.env` исключены через `.gitignore`.

Если Git попросит имя и email автора, задайте их для этого репозитория и повторите коммит:

```bash
git config user.name "Ваше имя"
git config user.email "Ваш email для GitHub"
```

Это данные автора коммитов. Они не заменяют логин GitHub. Можно использовать свой GitHub noreply email из настроек аккаунта.

## 4. Подключить GitHub

Скопируйте HTTPS URL из созданного репозитория. В примере ниже **замените `YOUR_LOGIN` на свой логин GitHub**, не на ФИО:

```bash
git remote add origin https://github.com/YOUR_LOGIN/orders-data-lab.git
git push -u origin main
```

Если Git попросит авторизоваться, выполните вход через предложенный им браузерный поток. Пароль GitHub нельзя использовать как пароль для HTTPS Git.

Если `origin` уже существует, сначала посмотрите `git remote -v` и проверьте адрес. Не меняйте адрес наугад и не используйте force push для первого размещения.

## 5. Посмотреть результат

Откройте репозиторий: README и изображение отчёта должны отображаться. На вкладке **Actions** появится workflow `Tests` с проверками SQLite и PostgreSQL. До фактического выполнения workflow его успешность не гарантирована.

Готовый HTML находится в `docs/demo-report/index.html`; GitHub показывает исходный код HTML. Для просмотра отчёта скачайте файл и откройте локально.

Для собственной доработки:

```bash
git switch -c feature/regional-analytics
```

После изменений и проверки:

```bash
git add .
git commit -m "Add regional sales analysis"
git push -u origin feature/regional-analytics
```

После этого можно открыть Pull Request на GitHub и описать, какую задачу решили, что изменили и как проверили результат.
