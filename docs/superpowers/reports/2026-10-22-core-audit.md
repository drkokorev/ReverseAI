# Аудит ядра ReverseAI — 2026-10-22

Ветка: `worktree-agent-a974919ef661d5b07` (от `main` @ `5fe4f36`). Каталог `src/reverseai/console/` не затрагивался.
Каждое исправление: сначала падающий регрессионный тест, затем исправление, отдельный коммит `fix: …`.

Итог проверки: `uv run pytest -q` — 480 passed, 5 skipped (docker); `uv run pytest -q -m browser tests/e2e` — 1 passed, 1 skipped (live, нет ключа); `uv run ruff check src tests` — чисто.

Новые решения: D-012 (барьер), D-013 (наблюдение), D-014 (строгие входные данные, общий журнал) в `docs/spec/decisions.md`, все — «инженерное решение (ждёт подтверждения)». Номер D-011 оставлен ветке веб-консоли.

## Часть A — известные пункты

### 1. D-010: роль `customer_lawyer` → `customer_analyst`
- `src/reverseai/barrier/release.py:59` — `Literal["operator", "customer_analyst"]`; `src/reverseai/cli.py:188`, подсказка `--role` в `approve`.
- README (пример и описание ролей, ссылка на D-010), план `docs/superpowers/plans/2026-10-20-foundation-and-web-pipeline.md`.
- Тесты: `tests/test_cli.py::test_approve_rejects_unknown_role` (старая роль теперь отклоняется), обновлены `tests/barrier/test_release.py`, `tests/test_pipeline.py`.

### 2. Остаточные риски барьера
- **2a. Предупреждения по строкам тел запросов.** `sanitizer.py:430` `body_warnings`, новый вид находки `body_warning` (`Finding`), `blocking()` (`sanitizer.py:104`); в `release.py` повторная проверка игнорирует предупреждения, черновик получил раздел «## Предупреждения», в отчёте — «предупреждение (тело запроса)». Значение не меняется; ключи и пути — только маскировка (D-008). Тесты: `test_body_values_seen_in_the_original_warn_but_release`, обновлён `test_long_paths_and_body_strings_survive_scenario_sanitizing`.
- **2b. Бренд внутри склеенных идентификаторов.** `sanitizer.py:312` `_mask_brand` (+ `_brand_pattern`, `_left_boundary`, `_right_boundary`, `_brand_spans`, `_glued`, `_same_case`): слова термина через пробел/`_`/`-`/`+`/`%20`/слитно, без учёта регистра, границы — не буквы/цифры, `%XX`, горб camelCase, цифра. Слитный бренд → название продукта без пробелов в регистре найденного (в путях — ASCII). Одно правило для прозы, идентификаторов и текстов индекса; идемпотентно, пути URL-безопасны. Тесты: `test_brand_glued_inside_identifiers_is_masked`, `test_brand_letters_inside_other_words_are_not_masked`, `test_glued_brand_in_prose_is_masked_too`.
- **2c. Согласованное переименование ключей.** `sanitizer.py:480` `KeyRenames`, `:570` `key_renames`, `:592` `_rename_schema`; одна карта на пакет строится в `release._sanitize` и применяется к телам, схемам запросов/ответов ApiContract, полям сущностей, указателям `json_equals`, картам `save`, `json_shape`. `withheld_expectations` (`sanitizer.py:782`) сопоставляет сохранённые ожидания по порядку (указатель или значение), поэтому переименованный указатель не считается удалённым. `parity/differential.py:151` `_clone_check`: клон проверяется выпущенными (переименованными) ожиданиями, удержанные добавляются только для подсчёта — раньше выпущенный указатель с новым именем не проверялся вовсе. Тесты: `test_renamed_body_keys_are_renamed_in_schema_pointers_and_save`, `test_withheld_expectations_follow_renamed_pointers`, `test_spec_schemas_and_entity_fields_share_the_scenario_renames`, `test_renamed_keys_agree_across_spec_and_scenarios_and_release`, `test_clone_check_uses_renamed_pointers_of_the_released_projection`.
- **2d. Потеря ведущего слэша.** `sanitizer.py:183` `_strip_origin`: `https://acme.com/api/x` → `/api/x` (находка `url`), домен в запросе по-прежнему → `original`. Тест `test_a_full_target_url_in_a_path_stays_an_absolute_path`; исправлено ожидание в `test_brand_and_domain_in_paths_become_url_safe`.
- **2e. Одно правило в обратной связи паритета.** `parity/feedback.py:46`: пути и указатели — через `mask_identifier` (как при выпуске), заголовок — выпущенный. «(path withheld)» больше не возникает для выпущенного пути. Тесты: `test_feedback_shows_released_paths_and_pointers_by_the_identifier_rule`, `test_feedback_masks_brand_in_a_path_or_pointer`, `test_feedback_uses_the_released_title`.

### 3. Отложенные мелкие находки (все подтвердились)
- **zones/store.py** — дедупликация по `(id, zone)` теряла kind/name: теперь запись индекса на каждые `(id, zone, kind, name)`, содержимое хранится один раз (`store.py:184`); `ref(..., kind=)`; `release._load_draft` ищет запись вида `release_draft`. Тест `test_same_content_under_another_kind_or_name_keeps_its_own_entry`.
- **observe/explorer.py** — WebSocket: в Playwright 1.64 есть `route_web_socket`; посторонние сокеты не подключаются и пишутся в `skipped` (`explorer.py:234`). `WebSocketRoute.close()` в синхронном API зависает внутри обработчика — поэтому сокет оставляется неподключённым (mock без сервера). Возврат после отправки формы ждёт `delay_s` (`:520`). Тесты: `test_explore_blocks_out_of_scope_websockets` (сырой TCP-сервер фиксировал Upgrade-запрос до исправления), `test_explore_sleeps_before_returning_to_a_page_a_form_left`.
- **sandbox/base.py:82** — проверка готовности `trust_env=False`. Тест `test_wait_ready_ignores_proxy_settings_of_the_environment`. Остальные клиенты к localhost уже были с `trust_env=False`.
- **implement/workspace.py:12, :85** — общий бюджет снимка `MAX_SNAPSHOT_CHARS = 200_000`; остальные файлы перечислены без содержимого. Тесты `test_snapshot_has_a_total_budget`, `test_snapshot_default_budget_bounds_the_prompt`.
- **implement/agent.py:63, :165** — защита файлов оракула без учёта регистра; `:447` — при исключении (LLMOutputError и т. п.) пишется `implement.done` с `passed: false`, номером итерации и ошибкой. Тесты `test_oracle_files_are_protected_whatever_the_letter_case`, `test_executor_output_error_still_records_implement_done`.
- **oracle/standalone.py:319** — `_stop_app` всегда шлёт группе SIGTERM, затем SIGKILL (раньше выход при завершившемся лидере оставлял детей); `:402` — OSError от Popen и некорректный сценарий → провал вида `error`, итоговая строка печатается. Тесты `test_stop_app_kills_the_group_even_when_the_leader_already_exited`, `test_standalone_main_reports_an_app_command_that_cannot_run`, `test_standalone_main_reports_a_malformed_scenario_and_goes_on`.
- **llm/jsonout.py:53** — интервалы пробуются от длинного к короткому, затем `_scan` (`:34`) — самое длинное значение от любой скобки; `RecursionError` ловится. Тесты `test_extract_json_prefers_the_outermost_span_over_bracketed_prose`, `test_extract_json_deep_nesting_is_an_output_error_not_a_crash`.
- **config** — `extra="forbid"` для всех моделей настроек (`config/__init__.py:14`), `RoleSpec.candidates` `min_length=1` (`:37`). Тесты `test_unknown_keys_are_rejected`, `test_a_role_needs_at_least_one_candidate`.
- **project.py:136** — гонка exists()+mkdir → `IntakeError`; проверка бренда не менялась. Тест `test_a_directory_created_concurrently_is_an_intake_error`.
- **audit/evidence.py:80, :112** — README без «ok»/«True»: «цел (проверка хэш-цепочки пройдена)» / «НАРУШЕНА», «Сходство ниже порога: да/нет». Тесты `test_readme_is_russian_without_english_status_tokens`, `test_readme_reports_a_tampered_ledger`, `test_readme_without_any_release`.

### 3+. Дополнительно (по запросу координатора) — общий журнал
- **provenance/ledger.py:96, :119** — `append` берёт блокировку потока и `fcntl.flock` на `ledger.jsonl.lock`, читает последнее валидное событие с конца файла и только потом сцепляет; два объекта/процесса больше не ветвят цепочку. Тесты `test_two_ledger_objects_on_one_file_keep_one_chain`, `test_two_processes_appending_keep_one_chain` (2 процесса × 50).

### 4. Ревью коммита c23021e (нажатия в исследователе)
Проверены защита области и записи (маршрутизатор контекста действует и для нажатий; на не-песочнице нажатий нет), лимит `max_clicks`, обработка диалогов, запись `ClickRecord`. Найдено и исправлено (`44d0bcb`):
- возврат на страницу после нажатия, уведшего с неё, шёл без паузы (`explorer.py:421`) — тест `test_explore_sleeps_before_returning_to_a_page_a_click_left`;
- всплывающее окно от нажатия (`window.open`) жило до конца обхода и обращалось к цели вне темпа — теперь закрывается сразу, пишется в `skipped` (`:541`) — тест `test_explore_closes_popups_a_click_opens`;
- страница, ушедшая во время чтения (скриншот/извлечение), роняла весь обход — теперь пропускается (`:495`) — тест `test_explore_skips_a_page_it_cannot_read_and_goes_on`.

## Часть B — найденные и исправленные ошибки
1. **Аудит бренда по другому правилу, чем барьер** (`audit/similarity.py:51`, `sanitizer.py:278` `has_brand`): `acme_id`, `AcmeTasks`, `/api/task-board`, `TaskBoard` проходили аудит. Тест `test_brand_mentions_use_the_barrier_brand_rule`.
2. **Опечатка в карточке проекта молча игнорировалась** (`project.py:32, :43`): `brand_term:` отключал маскировку бренда, `target_is_sanbox:` — флаг песочницы. Тест `test_unknown_card_keys_are_rejected`.
3. **Пустое имя согласующего** (`barrier/release.py:58, :65`): выпуск с `--approver ""`. Тест `test_approve_requires_an_approver_name`.
4. **Хранилище не видело артефактов другого процесса** (`zones/store.py:98`): индекс читался один раз — консоль рядом с CLI получала KeyError; теперь перечитывается при изменении размера, запись — под `fcntl.flock`. Тест `test_a_second_store_on_the_same_root_sees_new_artifacts`.
5. **Повторный stop() сервиса мог послать сигнал чужой группе процессов** (`sandbox/local.py:90`): после неудачного `CloneService.restart` старый хэндл останавливался второй раз по уже освобождённому pgid. Тест `test_a_second_stop_never_signals_a_reaped_process_group`.
6. Из пункта 4 части A: WebSocket-утечка, всплывающие окна, падение на уходящей странице (см. выше).

## Не исправлено (с причинами)
- WebSocket к самой цели на не-песочнице пропускается: сообщения сокета могут менять данные, но классифицировать их как «запись» нельзя без разбора протокола; блокировать все сокеты — потерять наблюдение. Вынесено в D-013 как открытый вопрос.
- Ключ, переименованный в теле (`Tasklet_2`), и тот же ключ в строке запроса пути (`?TaskBoard=1` → `tasklet`) маскируются разными правилами (идентификатор vs путь); на практике бренд в именах параметров запроса редок.
- Удержанное значение под переименованным указателем считается в `withheld_mismatches` всегда (клон отвечает новым именем); счётчик информационный, на порог не влияет.
- Индексы `_click_controls` берутся из `evaluate_all` и могут сдвинуться, если DOM перерисуется между чтением и нажатием (запись `ClickRecord` может назвать не тот элемент) — только неточность журнала.
- `_DESTRUCTIVE_RE` ловит и «clearly»/«cancellation» — ложные срабатывания только в журнале, сторона безопасности.
- `state.json` и `workspace_dir` при одновременной работе CLI и консоли — «последний пишущий выигрывает»; нужна общая модель блокировок фаз (задача веб-консоли).
- `CloneService.restart`, упавший посреди паритета, завершает весь `build` ошибкой «clone service did not start» вместо пометки сценария — редкий случай, поведение безопасное.
- `OpenAICompatProvider` ожидает строковый `content`; составной ответ (список частей) не поддерживается — у используемых моделей не встречается.
- `ScenarioStep` из чужого (не выпущенного) сценария в паритете (`projections.get(id, scenario)`) недостижим в конвейере: выпуск всегда содержит все id.
- Цикл обхода в `_brand_spans` при неудачной границе сдвигается на 1 символ; на 20-МБ бандлах это линейно в обычном случае, отдельной оптимизации не делалось.
