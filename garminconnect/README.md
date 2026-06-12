# Garmin Connect Python API — garminconnect/__init__.py API Reference

## Validation and Utility Functions

### `_validate_date_format(date_str: str, param_name: str = "date") -> str`
- **Purpose:** Validates that `date_str` is a string in `YYYY-MM-DD` format and is a real date.
- **Params:**
  - `date_str`: String representing a date.
  - `param_name`: Name used in error messages.
- **Returns:** The validated date string.
- **Raises:** ValueError if invalid.

---

### `_validate_positive_number(value: int | float, param_name: str = "value") -> int | float`
- **Purpose:** Ensures value is a real positive number (not zero or negative).
- **Params:**
  - `value`: Number to validate.
  - `param_name`: Name used in error messages.
- **Returns:** The original value if valid.
- **Raises:** ValueError if not positive or not a real number.

---

### `_validate_non_negative_integer(value: int, param_name: str = "value") -> int`
- **Purpose:** Ensures value is an integer >= 0.
- **Params:**
  - `value`: Integer to validate.
  - `param_name`: Name used in error messages.
- **Returns:** The integer if valid.
- **Raises:** ValueError if negative or not an integer.

---

### `_validate_positive_integer(value: int, param_name: str = "value") -> int`
- **Purpose:** Ensures value is a positive integer (> 0).
- **Params:**
  - `value`: Integer to validate.
  - `param_name`: Name used in error messages.
- **Returns:** The integer if valid.
- **Raises:** ValueError if zero/negative or not an integer.

---

### `_fmt_ts(dt: datetime) -> str`
- **Purpose:** Formats Python `datetime` into a string with millisecond precision for API requests.
- **Params:**
  - `dt`: Python `datetime` object.
- **Returns:** String timestamp in `"YYYY-MM-DDTHH:MM:SS.sss"` (ms) format.

---

### `_validate_json_exists(response: requests.Response) -> dict[str, Any] | None`
- **Purpose:** Checks if an HTTP response has JSON content; returns parsed JSON or `None` for 204 responses.
- **Params:**
  - `response`: HTTP response object.
- **Returns:** Parsed JSON (dict) or `None`.

---

## Core API Class

### `class Garmin`

- **Purpose:** Main interface for logging in, interacting with, and retrieving/sending data to/from Garmin Connect.
- **Public API Methods:**

#### Session & Auth
- `login(tokenstore: str | None = None) -> tuple[str | None, str | None]`: Log in using Garth. Returns tokens.
- `resume_login(client_state: dict[str, Any], mfa_code: str) -> tuple[Any, Any]`: Complete login with existing state and MFA code.

#### User Info
- `get_full_name() -> str | None`: Returns the full name.
- `get_unit_system() -> str | None`: Returns the user's unit system.

#### User Profile
- `get_user_profile() -> dict[str, Any]`: Get all user settings.
- `get_userprofile_settings() -> dict[str, Any]`: Get user profile settings.

#### Daily/Weekly Activity & Body Metrics
- `get_stats(cdate: str) -> dict[str, Any]`: Activity summary for a date (`YYYY-MM-DD`).
- `get_user_summary(cdate: str) -> dict[str, Any]`: Activity/user summary for a date.
- `get_steps_data(cdate: str) -> list[dict[str, Any]]`: Steps data for a date.
- `get_floors(cdate: str) -> dict[str, Any]`: Floors data for a date.
- `get_daily_steps(start: str, end: str) -> list[dict[str, Any]]`: Steps data for a date range.
- `get_weekly_steps(end: str, weeks: int = 52) -> list[dict[str, Any]]`: Weekly step aggregates.
- `get_weekly_stress(end: str, weeks: int = 52) -> list[dict[str, Any]]`: Weekly stress aggregates.
- `get_weekly_intensity_minutes(start: str, end: str) -> list[dict[str, Any]]`: Weekly intensity minutes.
- `get_heart_rates(cdate: str) -> dict[str, Any]`: Heart rate data for a date.
- `get_body_composition(startdate: str, enddate: str | None = None) -> dict[str, Any]`: Body composition records.
- `add_body_composition(...) -> dict[str, Any]`: Add body composition record.
- `add_weigh_in(weight: int | float, unitKey: str = "kg", timestamp: str = "") -> dict[str, Any] | None`: Add a weigh-in.
- `get_weigh_ins(startdate: str, enddate: str) -> dict[str, Any]`: Get weigh-ins between dates.
- `get_daily_weigh_ins(cdate: str) -> dict[str, Any]`: Get weigh-ins for one date.
- `delete_weigh_in(weight_pk: str, cdate: str) -> Any`: Delete a specific weigh-in.

#### Body Battery & Hydration
- `get_body_battery(startdate: str, enddate: str | None = None) -> list[dict[str, Any]]`: Get body battery data.
- `get_hydration_data(cdate: str) -> dict[str, Any]`: Get hydration data for a date.
- `add_hydration_data(value_in_ml: float, ...) -> Any`: Add hydration record.

#### Blood Pressure
- `set_blood_pressure(systolic: int, diastolic: int, timestamp: str = "") -> Any`: Add blood pressure.
- `get_blood_pressure(startdate: str, enddate: str | None = None) -> dict[str, Any]`: Get blood pressure records.
- `delete_blood_pressure(version: str, cdate: str) -> dict[str, Any]`: Delete blood pressure record.

#### Activities
- `count_activities() -> int`: Get total activities count.
- `get_activities(start: int = 0, limit: int = 20) -> list[dict[str, Any]]`: Get activities (paged).
- `upload_activity(activity_path: str) -> Any`: Upload a FIT file activity.
- `delete_activity(activity_id: str) -> Any`: Delete an activity by ID.
- `get_last_activity() -> dict[str, Any] | None`: Get the most recent activity.
- `get_activity(activity_id: str) -> dict[str, Any]`: Get summary for specified activity.

#### Sleep/Stress
- `get_sleep_data(cdate: str) -> dict[str, Any]`: Sleep data for a date.
- `get_stress_data(cdate: str) -> dict[str, Any]`: Daily stress data for a date.
- `get_all_day_stress(cdate: str) -> dict[str, Any]`: All-day stress for a date.

#### Devices
- `get_devices() -> list[dict[str, Any]]`: List of connected devices.
- `get_device_settings(device_id: str) -> dict[str, Any]`: Device settings by ID.
- `get_primary_training_device() -> dict[str, Any]`: Primary (preferred) device info.

#### Gear
- `get_gear(userProfileNumber: str) -> dict[str, Any]`: Get gear info.
- `get_gear_stats(gearUUID: str) -> dict[str, Any]`: Statistics for one gear.
- `add_gear_to_activity(gearUUID: str, activity_id: int | str) -> dict[str, Any]`: Assign gear to activity.

#### Workout APIs
- `get_workouts(start: int = 0, limit: int = 100) -> dict[str, Any]`: List of user workouts.
- `get_workout_by_id(workout_id: int | str) -> dict[str, Any]`: Download a workout by ID.

#### Other and Utility
- Many more endpoints exist for advanced user/health stats, badge, challenge, and event retrieval, and exercise analysis.

---

## Exception Classes

- `class GarminConnectConnectionError(Exception):`
  - Raised when a connection to Garmin Connect fails (network issues, etc).
- `class GarminConnectTooManyRequestsError(Exception):`
  - Raised for HTTP 429 “Too Many Requests”/rate-limiting.
- `class GarminConnectAuthenticationError(Exception):`
  - Raised when login/authentication fails.
- `class GarminConnectInvalidFileFormatError(Exception):`
  - Raised if file formats are incorrect/unsupported for upload/download.

---

## Example Usage of Core API

```python
from garminconnect import Garmin

# Login
client = Garmin(email="user@email.com", password="mypassword")
client.login()

# Get body weight samples
weights = client.get_body_weight()
```
