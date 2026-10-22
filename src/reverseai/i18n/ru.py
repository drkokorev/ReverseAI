"""Russian catalog. Keys and placeholders match `en.py` one to one.

Entries are `str.format` templates; a dict holds plural forms (`one`, `few`, `many`) chosen by
the `count` parameter. This file is the only place in `src/` where Cyrillic text lives (besides
the explorer's patterns for a target's own Russian buttons).
"""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {
    # Shared words
    "common.none": "нет",
    "common.yes": "да",
    "common.no": "нет",
    "common.of": "{part} из {whole}",
    # Pipeline phases (labels in messages) and their short timeline names
    "phase.intake": "Приём проекта",
    "phase.observe": "Наблюдение",
    "phase.oracle": "Оракул поведения",
    "phase.spec": "Спецификация",
    "phase.prepare_release": "Подготовка выпуска",
    "phase.release": "Выпуск через барьер",
    "phase.implement": "Реализация",
    "phase.parity": "Проверка паритета",
    "phase.audit": "Аудит",
    "phase_done": "Этап «{label}» ({phase}) завершён.",
    "stage.intake": "ПРИЁМ",
    "stage.observe": "НАБЛЮДЕНИЕ",
    "stage.oracle": "ОРАКУЛ",
    "stage.spec": "СПЕЦИФИКАЦИЯ",
    "stage.prepare_release": "ПОДГОТОВКА",
    "stage.release": "БАРЬЕР",
    "stage.implement": "РЕАЛИЗАЦИЯ",
    "stage.parity": "ПАРИТЕТ",
    "stage.audit": "АУДИТ",
    "zone_note.dirty": "Видит оригинал",
    "zone_note.released": "Пакет после барьера",
    "zone_note.clean": "Код клона",
    "zone_note.verifier": "Отчёты проверки",
    # Errors shared by the CLI and the console
    "error.intake": "проверка проекта не пройдена",
    "error.release": "выпуск через барьер отклонён",
    "error.policy": "политика данных запрещает вызов модели",
    "error.gateway": "ни одна модель не ответила",
    "error.llm_output": "некорректный ответ модели",
    "error.yaml": "некорректный YAML",
    "error.phase_order": "сначала завершите этап «{label}» ({phase})",
    "error.validation": "некорректные данные ({title}): {summary}",
    "validation.extra_forbidden": "неизвестное поле",
    "validation.missing": "обязательное поле не задано",
    "validation.json_invalid": "некорректный JSON",
    "validation.string_type": "ожидается строка",
    "validation.string_too_short": "не может быть пустым",
    "validation.bool_type": "ожидается true или false",
    "validation.int_type": "ожидается целое число",
    "validation.float_type": "ожидается число",
    "validation.list_type": "ожидается список",
    "validation.dict_type": "ожидается объект",
    "validation.invalid": "недопустимое значение",
    "validation.more": "и ещё {count}",
    # Intake gate (project card, observation scope)
    "intake.no_usable_characters": "в названии проекта «{name}» нет букв или цифр",
    "intake.attestation_required": "нужна аттестация законного доступа к цели",
    "intake.host_not_allowed": "хост цели «{host}» не входит в allowed_domains",
    "intake.product_reuses_brand": "название продукта «{name}» повторяет бренд оригинала",
    "intake.project_exists": "каталог проекта уже существует: {path}",
    "intake.observe_needs_sandbox": (
        "отправка форм и зондирование требуют card.target_is_sandbox"
    ),
    "intake.replay_needs_sandbox": "повтор сценариев на оригинале требует card.target_is_sandbox",
    "intake.submit_forms_needs_sandbox": (
        "submit_forms требует цель-песочницу (card.target_is_sandbox)"
    ),
    "intake.explorer_domains_subset": (
        "allowed_domains обходчика должны входить в allowed_domains карточки"
    ),
    "intake.start_host_not_allowed": "хост start_url «{host}» не входит в allowed_domains",
    "intake.probe_needs_sandbox": "зондирование пишет в цель и требует card.target_is_sandbox",
    "intake.probe_host_not_allowed": "хост зондирования «{host}» не входит в allowed_domains",
    "project.busy": (
        "проект занят другим процессом: {path} (выполняется другая команда или задача "
        "консоли). Дождитесь её завершения и повторите."
    ),
    # Barrier
    "release_error.product_name": (
        "название продукта в спецификации {spec} не совпадает с карточкой проекта: {card}"
    ),
    "release_error.no_artifact": "в грязной зоне нет артефакта {ref}",
    "release_error.not_a_draft": "артефакт {ref} — это {kind}, а не release_draft",
    "release_error.malformed": "черновик выпуска {ref} повреждён: {detail}",
    "release_error.approval_mismatch": "согласование не совпадает с хешем пакета черновика",
    "release_error.package_mismatch": (
        "спецификация и сценарии черновика не совпадают с записанным хешем пакета"
    ),
    "release_error.spec_mismatch": "спецификация черновика не совпадает со своим записанным хешем",
    "release_error.not_clean": "при повторной проверке черновик не чист: {where}",
    "release_error.would_drop": (
        "сценарии черновика содержат значения, которые санитайзер удалил бы"
    ),
    "release.draft_for_review": "Черновик для согласования: {path}",
    "release.package_sha": "SHA-256 пакета (спецификация + сценарии): {sha}",
    "release.body_warning_note": (
        "Строки тел запросов совпадают с кодом или текстом оригинала. Сценарий отправляет "
        "их как есть: проверьте, что это данные, а не выражение оригинала."
    ),
    "finding.code": "код",
    "finding.verbatim": "дословный текст",
    "finding.brand": "бренд",
    "finding.url": "домен",
    "finding.body_warning": "предупреждение (тело запроса)",
    # Spec markdown
    "spec_md.title": "{product} — поведенческая спецификация v{version}",
    "spec_md.overview": "Обзор",
    "spec_md.features": "Функции",
    "spec_md.entities": "Сущности",
    "spec_md.rules": "Правила",
    "spec_md.api": "API",
    "spec_md.gaps": "Пробелы",
    "spec_md.confidence": "уверенность: {confidence}",
    "spec_md.request": "запрос",
    "spec_md.response": "ответ {status}",
    # Release draft markdown (what the approver reads)
    "release_md.scenarios": "Сценарии",
    "release_md.critical": "критичный",
    "release_md.body": "тело",
    "release_md.status": "статус {status}",
    "release_md.shape": "форма",
    "release_md.save": "сохранить",
    "release_md.withheld": "Удалённые ожидаемые значения",
    "release_md.withheld_row": "{scenario}, шаг {step}: `{pointer}`",
    "release_md.warnings": "Предупреждения",
    "release_md.report": "Отчёт санитайзера",
    "release_md.package_sha": "SHA-256 пакета (спецификация + сценарии): `{sha}`",
    "release_md.spec_sha": "SHA-256 спецификации: `{sha}`",
    "release_md.scenario_count": "Сценариев: {count}",
    # Build, parity and audit lines (CLI output and console job logs)
    "build.local_sandbox_warning": "Внимание: LocalSandbox не изолирует код клона от этой машины.",
    "build.parity_line": (
        "Паритет: {passed}/{total} ({ratio:.2%}), критичные: {critical_passed}/{critical_total} "
        "({critical_ratio:.2%}), нестабильных: {unstable}"
    ),
    "build.skipped_unsafe": "Пропущено сценариев с записью (цель не песочница): {count}",
    "build.withheld_mismatches": "Расхождений по удержанным значениям: {count}",
    "build.workdir": "Рабочий каталог клона: {path}",
    "build.threshold_met": "Порог достигнут.",
    "build.threshold_missed": "Порог не достигнут.",
    "audit.pack": "Пакет доказательств: {path}",
    "audit.similarity": "Максимальное сходство кода: {score:.4f} (порог {threshold})",
    "audit.brand_hits": "Упоминаний бренда в коде: {count}",
    "audit.failed": "Аудит не пройден.",
    # Evidence pack README
    "evidence.title": "Пакет доказательств: {product}",
    "evidence.ledger": "Целостность журнала",
    "evidence.ledger_ok": "Статус: цел (проверка хэш-цепочки пройдена)",
    "evidence.ledger_broken": "Статус: НАРУШЕНА",
    "evidence.ledger_count": "Записей в журнале: {count}",
    "evidence.ledger_first_broken": "Первая нарушенная запись: {line} ({reason})",
    "evidence.approvals": "Одобрения",
    "evidence.approval": (
        "{approver} ({role}), {approved_at}, sha256 пакета (спецификация + сценарии): {sha}"
    ),
    "evidence.no_approvals": "Одобренных релизов нет.",
    "evidence.parity": "Паритет",
    "evidence.parity_ratio": "Доля пройденных сценариев: {ratio:.3f}",
    "evidence.parity_critical": "Доля критичных сценариев: {ratio:.3f}",
    "evidence.parity_total": "Всего сценариев: {count}",
    "evidence.parity_unstable": "Нестабильных сценариев: {count}",
    "evidence.parity_skipped": "Пропущено сценариев с записью (цель не песочница): {count}",
    "evidence.parity_withheld": "Расхождений по удержанным значениям: {count}",
    "evidence.similarity": "Сходство кода",
    "evidence.similarity_max": "Максимальное сходство: {score:.4f} при пороге {threshold}",
    "evidence.similarity_below": "Сходство ниже порога: {answer}",
    "evidence.brand": "Упоминания бренда",
    "evidence.brand_none": "Упоминаний не найдено.",
    "evidence.sandbox": "Песочница реализации",
    "evidence.sandbox_never": "Реализация не запускалась.",
    "evidence.sandbox_isolated": "Песочница: изолирована",
    "evidence.sandbox_not_isolated": (
        "Песочница: не изолирована (LocalSandbox: код клона выполнялся на машине оператора "
        "без изоляции файловой системы и сети)"
    ),
    "evidence.risks": "Риски приёма",
    "evidence.risks_none": "Нет.",
    "evidence.models": "Модели",
    "evidence.model_row": "{model} ({provider}): вызовов {count}, стоимость ${cost:.4f}",
    "evidence.models_none": "LLM-вызовов не было.",
    "evidence.disclaimer": "Документ не является юридическим заключением.",
    # CLI
    "cli.error": "Ошибка: {message}",
    "cli.environment_error": "Ошибка окружения: {message}",
    "cli.project_not_found": "проект не найден: {path}",
    "cli.card_not_found": "файл карточки не найден: {path}",
    "cli.bad_lang": "язык «{value}» не поддерживается: укажите {choices} (или задайте {env})",
    "cli.init.created": "Проект создан: {path}",
    "cli.init.flags": "Флаги риска: {flags}",
    "cli.prepare_release.next": (
        "Для выпуска: reverseai approve --project {project} --approver <ФИО> "
        "--role <operator|customer_analyst> --sha {sha}"
    ),
    "cli.approve.released": "Выпуск согласован: {ref}",
    "cli.build.unstable_refused": (
        "выпущенные сценарии изменяют данные цели, а сбросить её между сценариями "
        "командная строка не умеет: результаты паритета будут нестабильны. "
        "Запустите с --allow-unstable, чтобы продолжить."
    ),
    "cli.ledger.ok": "Журнал цел: цепочка хэшей не нарушена, событий: {count}",
    "cli.ledger.broken": "Целостность журнала нарушена: строка {line} ({reason})",
    "cli.costs.calls": "Вызовов LLM: {count}",
    "cli.costs.total": "Стоимость, USD: {total:.4f}",
    "cli.costs.by_role": "По ролям:",
    "cli.costs.by_model": "По моделям:",
    "cli.costs.row": "  {key}: вызовов {count}, {cost:.4f} USD",
    "cli.status.project": "Проект: {name} ({path})",
    "cli.status.completed": "Завершённые этапы:",
    "cli.status.artifacts": "Артефакты:",
    "cli.status.no_artifacts": "Артефакты: нет",
    "cli.status.rounds": "Раундов паритета: {count}",
    "cli.bench.offline": (
        "Офлайн-прогон бенчмарка (сценарная модель вместо LLM) выполняется только в тестах: "
        "uv run pytest tests/e2e. Для прогона с реальными моделями укажите --live."
    ),
    "cli.bench.target": "Бенчмарк: {target}",
    "cli.bench.scenarios": "Сценариев: {count}",
    "cli.bench.parity": "Паритет: {ratio:.2%}, критичные: {critical:.2%}",
    "cli.bench.hidden": "Скрытые тесты: {passed}/{total}",
    "cli.bench.similarity": "Максимальное сходство кода: {score:.4f}",
    "cli.bench.duration": "Длительность, с: {seconds:.1f}",
    "cli.bench.result": "Результат: {path}",
    "cli.console.token_required": (
        "адрес {host} доступен не только с этой машины: задайте токен доступа "
        "в переменной окружения {env} или запустите консоль на 127.0.0.1"
    ),
    "cli.console.url": "Консоль ReverseAI: {url}",
    "cli.console.login": "Вход: {url}/login (токен — значение {env})",
    "cli.console.stop": "Остановить: Ctrl+C",
    "cli.help.app": "ReverseAI: конвейер чистой комнаты для веб-приложений.",
    "cli.help.lang": "Язык интерфейса: en или ru (по умолчанию REVERSEAI_LANG, иначе en).",
    "cli.help.project": "Каталог проекта.",
    "cli.help.init": "Создать проект из карточки (юридический фильтр).",
    "cli.help.card": "Карточка проекта (YAML).",
    "cli.help.projects_root_init": "Каталог, в котором создаётся проект.",
    "cli.help.observe": "Наблюдение: обход цели в браузере и (для песочницы) зондирование API.",
    "cli.help.oracle": "Построить исполнимые сценарии поведения.",
    "cli.help.spec": "Составить поведенческую спецификацию (аналитик + критик).",
    "cli.help.prepare_release": "Очистить спецификацию и подготовить черновик к согласованию.",
    "cli.help.approve": "Согласовать черновик и выпустить его в чистую зону.",
    "cli.help.approver": "Кто согласует.",
    "cli.help.role": "operator (оператор платформы) или customer_analyst (аналитик заказчика).",
    "cli.help.sha": "SHA-256 согласуемого пакета (спецификация + сценарии).",
    "cli.help.build": (
        "Реализация в чистой зоне и проверка паритета (код выхода 2, если порог не достигнут)."
    ),
    "cli.help.allow_unstable": (
        "Запустить, хотя сценарии изменяют данные песочницы, а сброса между ними нет."
    ),
    "cli.help.audit": (
        "Аудит сходства кода и пакет доказательств (код выхода 2, если аудит не пройден)."
    ),
    "cli.help.out": "Каталог для пакета доказательств.",
    "cli.help.ledger_verify": "Проверить целостность журнала происхождения.",
    "cli.help.costs": "Сводка расходов на LLM по журналу.",
    "cli.help.status": "Показать завершённые этапы и ссылки на артефакты.",
    "cli.help.bench": "Прогнать весь конвейер на эталонной цели и посчитать метрики.",
    "cli.help.target": "Эталонная цель (bench/targets).",
    "cli.help.live": "Реальные модели из переменных окружения.",
    "cli.help.workdir": "Каталог прогона.",
    "cli.help.console": (
        "Веб-консоль: проекты, этапы, согласование выпуска, паритет и пакет доказательств."
    ),
    "cli.help.projects_root": "Каталог с проектами.",
    "cli.help.host": "Адрес сервера (по умолчанию только эта машина).",
    "cli.help.operator": "Имя оператора: инициалы в шапке, подписант по умолчанию.",
    "cli.help.console_lang": (
        "Язык консоли по умолчанию: en или ru (каждый зритель может переключить его в шапке)."
    ),
    # Console: shared services
    "console.no_provider_key": (
        "не задан ключ ни одного провайдера LLM: задайте переменную окружения ({names}) "
        "и перезапустите консоль"
    ),
    "console.operator_initials": "ОП",
    "console.build_label": "Реализация и паритет",
    "console.prepare_release.next": "Для выпуска согласуйте пакет на странице «Согласование».",
    "console.build.unstable_refused": (
        "выпущенные сценарии изменяют данные цели, а сбросить её между сценариями "
        "консоль не умеет: результаты паритета будут нестабильны. "
        "Отметьте «Разрешить нестабильный прогон», чтобы продолжить."
    ),
    "console.already_released": (
        "пакет уже выпущен. Чтобы выпустить новый, повторите подготовку выпуска."
    ),
    "console.draft_changed": "черновик изменился — обновите страницу и проверьте пакет заново",
    "registry.unreadable_file": "файл не читается ({error})",
    "registry.bad_card": "карточка повреждена: {problem}",
    "registry.bad_state": "состояние конвейера повреждено: {problem}",
    "role.operator": "Оператор платформы",
    "role.customer_analyst": "Аналитик заказчика",
    "role.recorded.operator": "оператор платформы",
    "role.recorded.customer_analyst": "аналитик заказчика",
    "role.recorded.customer_lawyer": "юрист заказчика (до D-010)",
    "mode.legacy": "LEGACY",
    "mode.import_substitution": "ИМПОРТОЗАМЕЩЕНИЕ",
    "mode_option.legacy": "Legacy (замена системы)",
    "mode_option.import_substitution": "Импортозамещение",
    "jurisdiction.us": "США",
    "jurisdiction.eu": "ЕС",
    "jurisdiction.cn": "Китай",
    "jurisdiction.self": "Собственный хостинг",
    "evidence_file.README": "сводка",
    "evidence_file.ledger": "журнал",
    "evidence_file.ledger_verification": "целостность",
    "evidence_file.release": "подписанный пакет",
    "evidence_file.sanitize_report": "очистка",
    "evidence_file.parity_report": "паритет",
    "evidence_file.similarity_report": "сходство",
    "evidence_file.models_used": "модели",
    "evidence_file.zones_access": "доступ зон",
    "evidence_outside": (
        "Пакет собран вне консоли (reverseai audit --out …): его здесь нет. Чтобы скачать "
        "пакет из консоли, повторите аудит на странице проекта."
    ),
    # Console: forms and actions
    "form.name_required": "Укажите название проекта.",
    "form.unknown_mode": "Неизвестный режим проекта.",
    "form.url_required": "Укажите адрес цели.",
    "form.domains_required": "Укажите хотя бы один разрешённый домен.",
    "form.product_required": "Укажите название продукта клона.",
    "form.jurisdiction_required": "Выберите хотя бы одну юрисдикцию.",
    "form.invalid_card": "Некорректные данные карточки: {summary}.",
    "form.intake.attestation_required": "Нужно подтвердить законность доступа к цели.",
    "form.intake.host_not_allowed": "Хост цели «{host}» не входит в разрешённые домены.",
    "form.intake.product_reuses_brand": "Название продукта «{name}» повторяет бренд оригинала.",
    "form.intake.project_exists": "Проект с таким именем уже существует.",
    "form.intake.no_usable_characters": "В названии проекта нет букв или цифр.",
    "phases.busy": "Для проекта уже выполняется задача «{label}». Дождитесь её завершения.",
    "phases.bad_max_pages": "Число страниц должно быть целым числом от 1.",
    "phases.bad_max_rounds": "Число раундов должно быть целым числом от 1.",
    "approve.approver_required": "Укажите, кто согласует пакет.",
    "approve.unknown_role": "Неизвестная роль согласующего.",
    "approve.confirm_required": "Подтвердите, что просмотрели пакет: отметьте флажок.",
    "approve.wait_job": "Дождитесь завершения задачи «{label}».",
    "job_status.running": "выполняется",
    "job_status.succeeded": "завершено",
    "job_status.attention": "требует внимания",
    "job_status.failed": "ошибка",
    "job.internal_error": "Внутренняя ошибка ({error}). Подробности — в журнале сервера.",
    # Console: error pages
    "errors.internal.title": "Внутренняя ошибка",
    "errors.internal.message": "Запрос не выполнен ({error}). Подробности — в журнале сервера.",
    "errors.project_not_found.title": "Проект не найден",
    "errors.project_not_found.message": "Проекта с таким именем нет в каталоге проектов.",
    "errors.project_invalid.title": "Проект повреждён",
    "errors.project_invalid.message": "Проект «{name}» не открывается: {reason}.",
    "errors.bad_request.title": "Некорректный запрос",
    "errors.bad_request.message": "Параметры запроса не прошли проверку.",
    "errors.bad_request.fields": "Поля: {fields}.",
    "errors.csrf.title": "Форма устарела",
    "errors.csrf.message": "Недействительный токен формы. Обновите страницу и повторите.",
    "errors.not_found.title": "Страница не найдена",
    "errors.not_found.message": "Такой страницы нет.",
    "errors.http.title": "Ошибка запроса",
    "errors.no_evidence.title": "Нет пакета доказательств",
    "errors.no_action.title": "Действие не найдено",
    "errors.no_action.message": "Нет такого этапа: «{action}».",
    "error_page.eyebrow": "ОШИБКА",
    "error_page.back": "К ПРОЕКТАМ",
    # Console: header
    "nav.label": "Разделы",
    "nav.projects": "ПРОЕКТЫ",
    "nav.overview": "ОБЗОР",
    "nav.release": "СОГЛАСОВАНИЕ",
    "nav.parity": "ПАРИТЕТ",
    "nav.costs": "РАСХОДЫ",
    "nav.ledger": "ЖУРНАЛ",
    "nav.language": "Язык",
    "nav.theme": "Переключить тему",
    "nav.operator": "Оператор",
    # Console: login
    "login.page_title": "Вход",
    "login.eyebrow": "ДОСТУП",
    "login.title": "Нужен токен доступа",
    "login.message": (
        "Консоль доступна не только с этой машины. Введите токен доступа или передайте "
        "заголовок Authorization: Bearer."
    ),
    "login.token_label": "Токен доступа (значение REVERSEAI_CONSOLE_TOKEN)",
    "login.submit": "ВОЙТИ",
    "login.wrong_token": "Неверный токен доступа.",
    # Console: projects list
    "projects.page_title": "Проекты",
    "projects.eyebrow": "КАТАЛОГ",
    "projects.title": "ПРОЕКТЫ",
    "projects.lede": (
        "Каждый проект проходит девять этапов: от приёма и наблюдения за целью до выпуска "
        "пакета через барьер, реализации, паритета и аудита."
    ),
    "projects.new": "НОВЫЙ ПРОЕКТ",
    "projects.all": "ВСЕ ПРОЕКТЫ",
    "projects.col.project": "ПРОЕКТ",
    "projects.col.mode": "РЕЖИМ",
    "projects.col.target": "ЦЕЛЬ",
    "projects.col.phases": "ЭТАПЫ",
    "projects.col.activity": "АКТИВНОСТЬ",
    "projects.broken": "Проект не открывается: исправьте файлы в каталоге проекта.",
    "projects.clone": "клон: {product}",
    "projects.sandbox": "песочница",
    "projects.progress": "Завершено этапов: {done} из 9",
    "projects.empty": (
        "Проектов пока нет. Создайте первый: карточка проекта, аттестация законного доступа "
        "и разрешённые домены."
    ),
    # Console: new project
    "new.page_title": "Новый проект",
    "new.eyebrow": "ЭТАП 01 · ПРИЁМ",
    "new.title": "НОВЫЙ ПРОЕКТ",
    "new.lede": (
        "Карточка проекта проходит юридический фильтр: законный доступ к цели, хост цели "
        "среди разрешённых доменов, название клона без бренда оригинала."
    ),
    "new.section.project": "ПРОЕКТ",
    "new.section.target": "ЦЕЛЬ",
    "new.section.policy": "ПОЛИТИКА ДАННЫХ",
    "new.section.attestation": "АТТЕСТАЦИЯ",
    "new.name": "Название проекта",
    "new.mode": "Режим",
    "new.product": "Название продукта клона",
    "new.product_hint": "Не должно повторять бренд оригинала.",
    "new.brand": "Бренд оригинала",
    "new.brand_hint": (
        "Через запятую или с новой строки. Вырезается из всего, что пересекает барьер."
    ),
    "new.url": "Адрес цели",
    "new.domains": "Разрешённые домены",
    "new.domains_hint": "Хост цели должен быть в списке. Через запятую или с новой строки.",
    "new.sandbox": (
        "Цель — песочница: разрешены отправка форм, зондирование API и сценарии с записью."
    ),
    "new.jurisdictions_label": "Юрисдикции провайдеров моделей",
    "new.jurisdictions_hint": "Модели вызываются только у провайдеров из выбранных юрисдикций.",
    "new.jurisdiction": "Юрисдикция проекта",
    "new.basis": "Основание доступа",
    "new.basis_placeholder": "Договор, лицензия, собственная система",
    "new.signed_by": "Кто подписал",
    "new.signed_at": "Когда подписано",
    "new.signed_at_hint": "ISO 8601. Пусто — текущее время.",
    "new.lawful_access": "Подтверждаю законный доступ к цели и право изучать её поведение.",
    "new.submit": "СОЗДАТЬ ПРОЕКТ",
    "new.cancel": "ОТМЕНА",
    # Console: project overview
    "overview.eyebrow": "ПРОЕКТ {name}",
    "overview.sandbox": "ПЕСОЧНИЦА",
    "overview.read_only": "ТОЛЬКО ЧТЕНИЕ",
    "overview.lede_intact": {
        "one": (
            "Независимая реимплементация цели по наблюдаемому поведению. Завершено {count} этап "
            "из 9, журнал происхождения цел."
        ),
        "few": (
            "Независимая реимплементация цели по наблюдаемому поведению. Завершено {count} "
            "этапа из 9, журнал происхождения цел."
        ),
        "many": (
            "Независимая реимплементация цели по наблюдаемому поведению. Завершено {count} "
            "этапов из 9, журнал происхождения цел."
        ),
    },
    "overview.lede_broken": {
        "one": (
            "Независимая реимплементация цели по наблюдаемому поведению. Завершено {count} этап "
            "из 9, журнал происхождения повреждён."
        ),
        "few": (
            "Независимая реимплементация цели по наблюдаемому поведению. Завершено {count} "
            "этапа из 9, журнал происхождения повреждён."
        ),
        "many": (
            "Независимая реимплементация цели по наблюдаемому поведению. Завершено {count} "
            "этапов из 9, журнал происхождения повреждён."
        ),
    },
    "overview.release": "ВЫПУСК",
    "overview.evidence": "ПАКЕТ ДОКАЗАТЕЛЬСТВ",
    "overview.track": "ТРАЕКТОРИЯ",
    "overview.stage.done": "Завершён",
    "overview.stage.awaiting_approval": "Ждёт согласования",
    "overview.stage.ready": "Можно запускать",
    "overview.stage.waiting": "Ожидает",
    "overview.kpis": "Ключевые показатели",
    "overview.zones": "ЗОНЫ",
    "overview.zones_note": (
        "Чистая зона читает только выпущенный пакет. Попытка чтения из грязной зоны "
        "блокируется и пишется в журнал."
    ),
    "overview.ledger": "ЖУРНАЛ ПРОИСХОЖДЕНИЯ",
    "overview.integrity_ok": {
        "one": "{count} событие · цепочка цела",
        "few": "{count} события · цепочка цела",
        "many": "{count} событий · цепочка цела",
    },
    "overview.integrity_broken": "Целостность нарушена: запись {line} ({reason})",
    "overview.filter": "Тип события начинается с",
    "overview.filter_submit": "ПОКАЗАТЬ",
    "overview.filter_all": "все",
    "overview.hide_artifacts": "скрыть артефакты",
    "overview.show_artifacts": "показать артефакты",
    "overview.col.time": "ВРЕМЯ",
    "overview.col.event": "СОБЫТИЕ",
    "overview.col.summary": "СВОДКА",
    "overview.col.zone": "ЗОНА",
    "overview.col.actor": "КТО",
    "overview.col.hash": "ХЕШ",
    "overview.no_events": "Событий с таким типом нет.",
    "overview.shown": "Показаны последние {shown} из {total}.",
    "overview.show_all": "Показать все",
    "overview.hidden_artifacts": "Скрыто событий artifact.*: {count} (запись и чтение артефактов).",
    "detail.intake": "Аттестация доступа; риски: {flags}",
    "detail.no_risks": "не найдены",
    "detail.pages": {
        "one": "{count} страница", "few": "{count} страницы", "many": "{count} страниц",
    },
    "detail.exchanges": {
        "one": "{count} обмен", "few": "{count} обмена", "many": "{count} обменов",
    },
    "detail.probes": {
        "one": "{count} проба API", "few": "{count} пробы API", "many": "{count} проб API",
    },
    "detail.scenarios": {
        "one": "{count} сценарий", "few": "{count} сценария", "many": "{count} сценариев",
    },
    "detail.dropped": "отброшено: {count}",
    "detail.features": {
        "one": "{count} функция", "few": "{count} функции", "many": "{count} функций",
    },
    "detail.rules": {
        "one": "{count} правило", "few": "{count} правила", "many": "{count} правил",
    },
    "detail.findings": "Находок санитайзера: {count}",
    "detail.signed": "Пакет {sha}… подписан",
    "detail.iterations": {
        "one": "{count} итерация", "few": "{count} итерации", "many": "{count} итераций",
    },
    "detail.parity": {
        "one": "{ratio:.3f} за {count} раунд",
        "few": "{ratio:.3f} за {count} раунда",
        "many": "{ratio:.3f} за {count} раундов",
    },
    "detail.audit_outside": "Пакет собран вне консоли",
    "detail.similarity": "Сходство {score:.3f}",
    "kpi.parity": "ПАРИТЕТ",
    "kpi.critical": "КРИТИЧНЫЕ",
    "kpi.similarity": "СХОДСТВО КОДА",
    "kpi.scenarios_passed": {
        "one": "{passed} из {count} сценария",
        "few": "{passed} из {count} сценариев",
        "many": "{passed} из {count} сценариев",
    },
    "kpi.no_report": "Нет отчёта",
    "kpi.threshold": "порог {threshold:.3f}",
    "kpi.audit_outside": "Аудит проведён вне консоли",
    "kpi.no_audit": "Аудит не проводился",
    "kpi.calls": {"one": "{count} вызов", "few": "{count} вызова", "many": "{count} вызовов"},
    "summary.phase": "этап {phase}",
    "summary.invalidated": "сброшены: {phases}",
    # Console: job panel and phase controls
    "job.title": "ЗАДАЧА",
    "job.started": "начало {time}",
    "job.finished": "конец {time}",
    "job.none": (
        "Задач в этом запуске консоли ещё не было. Этапы запускаются кнопками ниже; "
        "одновременно выполняется одна задача на проект."
    ),
    "run.title": "ЗАПУСК ЭТАПОВ",
    "run.invalidates": "Повторный запуск этапа сбрасывает все следующие этапы.",
    "run.done": "готово",
    "run.rerun": "ПОВТОРИТЬ",
    "run.start": "ЗАПУСТИТЬ",
    "run.observe.title": "НАБЛЮДЕНИЕ",
    "run.observe.note": "Обход цели в браузере; на песочнице — формы и зондирование API.",
    "run.max_pages": "Страниц, не больше",
    "run.submit_forms": "Отправлять формы",
    "run.probe": "Зондировать API",
    "run.read_only": "Цель не песочница: только чтение.",
    "run.oracle.title": "ОРАКУЛ",
    "run.oracle.note": "Исполнимые сценарии поведения из наблюдённых обменов.",
    "run.spec.title": "СПЕЦИФИКАЦИЯ",
    "run.spec.note": "Аналитик и критик составляют поведенческую спецификацию (вызовы LLM).",
    "run.prepare.title": "ПОДГОТОВКА ВЫПУСКА",
    "run.prepare.note": "Санитайзер очищает спецификацию и сценарии; черновик ждёт согласования.",
    "run.build.title": "РЕАЛИЗАЦИЯ И ПАРИТЕТ",
    "run.build.note": "Агенты пишут клон в чистой зоне; паритет сравнивает его с оригиналом.",
    "run.max_rounds": "Раундов, не больше",
    "run.allow_unstable": "Разрешить нестабильный прогон",
    "run.local_sandbox": "LocalSandbox не изолирует код клона от этой машины.",
    "run.audit.title": "АУДИТ",
    "run.audit.note": "Сходство кода, упоминания бренда и пакет доказательств.",
    # Console: costs
    "costs.page_title": "Расходы · {name}",
    "costs.eyebrow": "ЖУРНАЛ",
    "costs.title": "РАСХОДЫ",
    "costs.lede_before": (
        "Все вызовы моделей идут через шлюз и записываются в журнал происхождения. Суммы "
        "совпадают с командой"
    ),
    "costs.lede_after": ".",
    "costs.totals": "Итоги",
    "costs.calls": "ВЫЗОВЫ LLM",
    "costs.calls_sub": "по журналу проекта",
    "costs.cost": "СТОИМОСТЬ",
    "costs.cost_sub": "USD по ценам из конфигурации",
    "costs.by_role": "ПО РОЛЯМ",
    "costs.by_model": "ПО МОДЕЛЯМ",
    "costs.col.role": "РОЛЬ",
    "costs.col.model": "МОДЕЛЬ (ПРОВАЙДЕР)",
    "costs.col.calls": "ВЫЗОВЫ",
    "costs.none": "Вызовов LLM не было.",
    # Console: parity and evidence
    "parity_page.page_title": "Паритет · {name}",
    "parity_page.eyebrow": "ЭТАПЫ 08–09",
    "parity_page.title": "ПАРИТЕТ",
    "parity_page.lede": (
        "Одни и те же сценарии запущены на оригинале и на клоне. Сравнение идёт по поведению "
        "и данным, не по внешнему виду."
    ),
    "parity_page.met": "ПОРОГ ПРОЙДЕН",
    "parity_page.missed": "ПОРОГ НЕ ДОСТИГНУТ",
    "parity_page.none_before": "Паритет ещё не проверялся. Запустите «Реализацию и паритет» на",
    "parity_page.none_link": "странице проекта",
    "parity_page.none_after": "после выпуска пакета.",
    "parity_page.totals": "Итоги",
    "parity_page.threshold": "порог {threshold:.2f}",
    "parity_page.unstable": "НЕСТАБИЛЬНЫЕ",
    "parity_page.unstable_sub": "не более {limit}%, критичные — ни одного",
    "parity_page.rounds": "РАУНДЫ",
    "parity_page.rounds_sub": "реализация → паритет",
    "parity_page.scenarios": "СЦЕНАРИИ",
    "parity_page.col.scenario": "СЦЕНАРИЙ",
    "parity_page.col.original": "ОРИГИНАЛ",
    "parity_page.col.clone": "КЛОН",
    "parity_page.col.failures": "РАСХОЖДЕНИЯ",
    "parity_page.unstable_short": "НЕСТАБ.",
    "parity_page.skipped": "пропущено сценариев с записью (цель не песочница): {count}",
    "parity_page.unstable_on_original": "нестабильны на оригинале: {ids}",
    "parity_page.allowed": "из допустимых {threshold:.3f}",
    "parity_page.meter": "Сходство {score:.3f} при пороге {threshold:.3f}",
    "parity_page.similarity_note": (
        "Доля фрагментов кода клона, совпадающих с кодом оригинала (JS/CSS), окно 8 токенов."
    ),
    "parity_page.brand_hits": "УПОМИНАНИЯ БРЕНДА",
    "parity_page.no_brand_hits": "Упоминаний бренда не найдено.",
    "parity_page.audit_outside": (
        "Аудит проведён вне консоли: его отчёт о сходстве — в пакете доказательств, собранном "
        "командой"
    ),
    "parity_page.no_audit": "Аудит ещё не проводился.",
    "parity_page.download": "СКАЧАТЬ",
    "parity_page.evidence_missing": "Пакет доказательств ещё не собран: запустите аудит.",
    "parity_page.not_isolated": (
        "Песочница реализации не изолирована (LocalSandbox): код клона выполнялся на машине "
        "оператора. В пакете это указано явно."
    ),
    "parity_page.handoff": (
        "Пакет передаётся юристу заказчика. Документ не является юридическим заключением."
    ),
    "scenario.critical": "критичный",
    "scenario.regular": "обычный",
    "scenario.step": "шаг {step}",
    # Console: release review
    "release_page.page_title": "Согласование · {name}",
    "release_page.eyebrow": "ЭТАП 06 · БАРЬЕР",
    "release_page.title": "ПАКЕТ v{version}",
    "release_page.lede": (
        "Всё, что увидят агенты-реализаторы: спецификация и сценарии после очистки. Подпись "
        "привязана к хешу пакета — после неё содержимое изменить нельзя."
    ),
    "release_page.no_draft_before": (
        "Черновик выпуска ещё не подготовлен. Запустите этап «Подготовка выпуска» на"
    ),
    "release_page.no_draft_after": ".",
    "release_page.contents": "Содержимое пакета",
    "release_page.tab.spec": "СПЕЦИФИКАЦИЯ",
    "release_page.tab.scenarios": "СЦЕНАРИИ",
    "release_page.tab.cleanup": "ОЧИСТКА",
    "release_page.features": "ФУНКЦИИ",
    "release_page.rules": "ПРАВИЛА",
    "release_page.entities": "СУЩНОСТИ",
    "release_page.gaps": "ПРОБЕЛЫ",
    "release_page.col.steps": "ЗАПРОСЫ И ОЖИДАНИЯ",
    "release_page.col.type": "ТИП",
    "release_page.no_scenarios": "Сценариев нет.",
    "release_page.findings": "НАХОДКИ",
    "release_page.warnings": "ПРЕДУПРЕЖДЕНИЯ",
    "release_page.withheld": "УДЕРЖАНО",
    "release_page.dropped": "ОТБРОШЕНО ОРАКУЛОМ",
    "release_page.sanitizer_note": (
        "Санитайзер сверяет каждый текст пакета со словарём оригинала: код, страницы, ответы "
        "сервера. Совпадения от 8 слов, бренд и домены вырезаются; длинные и прозаические "
        "ожидаемые значения не передаются."
    ),
    "release_page.sanitizer_findings": "НАХОДКИ САНИТАЙЗЕРА",
    "release_page.no_findings": "Санитайзер ничего не нашёл.",
    "release_page.warnings_note": (
        "Строки тел запросов совпадают с кодом или текстом оригинала. Сценарий отправляет их "
        "как есть, выпуск они не блокируют: проверьте, что это данные, а не выражение "
        "оригинала."
    ),
    "release_page.withheld_title": "УДЕРЖАННЫЕ ОЖИДАЕМЫЕ ЗНАЧЕНИЯ",
    "release_page.nothing_withheld": "Ничего не удержано.",
    "release_page.not_replayed": "Сценарии не перепроверялись на сброшенном оригинале.",
    "release_page.not_reproduced": "не воспроизводится на чистом оригинале",
    "release_page.nothing_dropped": "Ничего не отброшено.",
    "release_page.signature": "Подпись",
    "release_page.signature_title": "ПОДПИСЬ ПАКЕТА",
    "release_page.package_sha": "SHA-256 пакета (спецификация + сценарии)",
    "release_page.readable_draft": "Черновик для чтения",
    "release_page.released": "ВЫПУЩЕНО",
    "release_page.released_note": (
        "Пакет передан в чистую зону. События barrier.approved и barrier.release записаны "
        "в журнал."
    ),
    "release_page.to_parity": "К ПАРИТЕТУ",
    "release_page.approver": "Подписант",
    "release_page.role": "Роль",
    "release_page.confirm": "Я просмотрел пакет: в нём нет кода, текстов и бренда оригинала.",
    "release_page.submit": "СОГЛАСОВАТЬ И ВЫПУСТИТЬ",
    "release_page.lawyer_note": (
        "Юрист заказчика получает итоговый пакет доказательств после аудита."
    ),
}
