# Garbage Collection

A Home Assistant helper that tracks a regular collection schedule (garbage, recycling, bio waste, or anything else that repeats). It gives you a sensor with the next date and the days remaining, and a shared calendar.

This is a maintained fork of [bruxy70/Garbage-Collection](https://github.com/bruxy70/Garbage-Collection), updated for current Home Assistant. It requires **Home Assistant 2025.10 or newer**.

<img src="images/picture-entity.png" alt="Collection sensors shown as pictures on a dashboard">

## Supported schedules

- `weekly`: one or more days each week, e.g. Tuesday and Thursday
- `even-weeks` / `odd-weeks`: by ISO week number
- `every-n-weeks`: every `period` weeks, offset by `first_week`. ISO week numbers restart each year; for a cadence that continues across New Year, use `every-n-days` with a multiple of 7
- `every-n-days`: every `period` days from `first_date`
- `monthly`: the n<sup>th</sup> weekday of the month (e.g. 1st and 3rd Wednesday), optionally every `period` months
- `annual`: once a year on a fixed date (e.g. birthdays)
- `group`: merges several sensors into one, showing the earliest next collection
- `blank`: no automatic dates; you add them yourself with [manual update](#manual-update)

Any schedule except `annual`, `group` and `blank` can be limited to part of the year with `first_month` and `last_month` (e.g. bio waste from April to November).

## Installation

**HACS:** in HACS, open the menu and choose *Custom repositories*. Add `https://github.com/darek-margas/Garbage-Collection` as an *Integration*, install **Garbage Collection**, and restart Home Assistant.

**Manual:** download `garbage_collection.zip` from the [latest release](https://github.com/darek-margas/Garbage-Collection/releases/latest), unpack it into `config/custom_components/garbage_collection/`, and restart Home Assistant. Don't keep backup copies inside `custom_components`: Home Assistant loads every folder there.

## Configuration

Go to *Settings → Devices & services → Helpers → Create helper → Garbage Collection*, and create one helper per schedule. Setup is in the UI only; YAML configuration is not supported.

### Step 1: common options

| Option | Description |
| :-- | :-- |
| Name | Sensor name |
| Frequency | One of the [schedules](#supported-schedules) above |
| Icon / Icon today / Icon tomorrow | Icons for a later, today's and tomorrow's collection. Defaults: `mdi:trash-can`, `mdi:delete-restore`, `mdi:delete-circle` |
| Expire after | Time (`HH:MM`). On collection day, move on to the next collection after this time, e.g. once the morning pickup has passed |
| Verbose state | Show text ("Today", "Tomorrow", "on 10-Sep-2026, in 3 days") instead of `0`/`1`/`2`. Formatting on the dashboard is usually the better choice |
| Hide in calendar | Leave this sensor out of the calendar, e.g. for members of a group |
| Manual update | Don't update the state automatically; see [manual update](#manual-update) |

### Step 2: schedule options

| Option | Used by | Description |
| :-- | :-- | :-- |
| Collection days | all except `every-n-days`, `annual`, `group`, `blank` | Days of the week |
| First month / Last month | all except `annual`, `group`, `blank` | Collection season. Default: January to December |
| Period | `every-n-weeks`, `every-n-days`, `monthly` | Repeat every n weeks, days or months. For `monthly`, the first month sets which months count |
| First week | `every-n-weeks` | ISO week number of the first collection, to offset the cadence. Keep it lower than the period |
| First date | `every-n-days` | Date the cadence starts from |
| Order of weekday | `monthly` | Which occurrences of the weekday, e.g. 1 and 3 for the 1st and 3rd Wednesday |
| Order of week instead of weekday | `monthly` | Use the weekday in the n<sup>th</sup> calendar week of the month instead. If a month starts on a Friday, the Wednesday of its 1st week falls in the previous month. Only enable this if your schedule really works that way |
| Date | `annual` | `mm/dd`, e.g. `11/24` |
| Entities | `group` | The sensors to merge |
| Verbose format / Date format | with verbose state | Text format with `{date}` and `{days}` placeholders, and the Python `strftime` date format. Defaults: `on {date}, in {days} days` and `%d-%b-%Y` |

## Sensor

| State | Meaning |
| :-- | :-- |
| `0` | Collection today |
| `1` | Collection tomorrow |
| `2` | Collection later |

| Attribute | Description |
| :-- | :-- |
| `next_date` | Date of the next collection (local midnight) |
| `days` | Days until the next collection |
| `last_collection` | When the last collection was marked as done |
| `last_updated` | When the sensor last recalculated |

The sensor recalculates at midnight, at the *expire after* time, when Home Assistant starts, and when a service is called. A group recalculates whenever one of its members does.

All sensors that aren't hidden appear in the **Garbage Collection** calendar.

## Services

All services target one or more garbage collection sensors.

| Service | Fields | Description |
| :-- | :-- | :-- |
| `garbage_collection.collect_garbage` | `last_collection` (optional) | Mark today's collection as done, so the sensor moves on to the next one. Defaults to now |
| `garbage_collection.add_date` | `date` | Add a collection date |
| `garbage_collection.remove_date` | `date` | Remove a calculated date |
| `garbage_collection.offset_date` | `date`, `offset` | Move a date by `offset` days (-31 to 31) |
| `garbage_collection.update_state` | | Recalculate the state from the current list of dates |

```yaml
action: garbage_collection.collect_garbage
target:
  entity_id: sensor.general_waste
```

## Manual update

Manual update lets an automation change the calculated dates, e.g. to move collections that fall on public holidays.

1. Enable *Manual update* on the sensor.
2. Each time the sensor recalculates, it fires a `garbage_collection_loaded` event with `entity_id` and `collection_dates` (the calculated dates), instead of updating its state.
3. An automation triggered by that event calls `add_date`, `remove_date` or `offset_date` as needed, and finishes with `update_state`.

The dates are calculated again on every update, so the changes have to be made by an automation that runs on every event.

```yaml
alias: Extra collection on 7 January
triggers:
  - trigger: event
    event_type: garbage_collection_loaded
    event_data:
      entity_id: sensor.general_waste
actions:
  - action: garbage_collection.add_date
    target:
      entity_id: "{{ trigger.event.data.entity_id }}"
    data:
      date: "2027-01-07"
  - action: garbage_collection.update_state
    target:
      entity_id: "{{ trigger.event.data.entity_id }}"
```

### Blueprints

Ready-made automations for manual update; click a name to import it into Home Assistant. The public holiday blueprints need the [Holidays](https://github.com/bruxy70/Holidays) helper.

| Blueprint | What it does |
| :-- | :-- |
| [Move on holiday](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fmove_on_holiday.yaml) | Move a collection that falls on a public holiday to the next day |
| [Move on holiday with include/exclude](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fmove_on_holiday_with_include_exclude.yaml) | Remove excluded dates, move holidays, then add included dates |
| [Holiday in week](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fholiday_in_week.yaml) | Move one day later if there was a holiday earlier in the week or on the day |
| [Multiple holidays in week](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fmultiple_holidays_in_week.yaml) | Move one day later for each holiday earlier in the week or on the day |
| [Move on holiday, carry over](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fmove_on_holiday_carry_over.yaml) | Move at most one day per week; further holidays carry over to the next week |
| [Skip holiday](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fskip_holday.yaml) | Drop collections that fall on a holiday |
| [Include and exclude](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Finclude_exclude.yaml) | Add and remove fixed dates |
| [Include](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Finclude.yaml) | Add fixed dates |
| [Exclude](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fexclude.yaml) | Remove fixed dates |
| [Offset](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Foffset.yaml) | Move all collections by a number of days, e.g. first Saturday minus 7 days = last Saturday of the previous month |
| [Monthly fixed date](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fmonthly_fixed_date.yaml) | A collection on a fixed day of each month, typically with `blank` |
| [Monthly two fixed dates](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fmonthly_fixed_two_dates.yaml) | Collections on two fixed days of each month, typically with `blank` |
| [Import TXT](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdarek-margas%2FGarbage-Collection%2Fblob%2Fmaster%2Fblueprints%2Fimport_txt.yaml) | Load dates from a text file through a `command_line` sensor, one date per line |

## Dashboard example

The `0`/`1`/`2` state works well with one picture per state; the pictures used here are in [`images/containers`](images/containers).

```yaml
type: picture-entity
entity: sensor.bio
show_state: false
state_image:
  "0": /local/containers/bio_today.png
  "1": /local/containers/bio_tomorrow.png
  "2": /local/containers/bio_off.png
```

There is also a dedicated [garbage collection card](https://github.com/amaximus/garbage-collection-card).

## License

MIT. Original work by [@bruxy70](https://github.com/bruxy70).
