from pathlib import Path
import csv

class Event:
    """
    Represent an event that occurs at a specific day and time.
    """

    def __init__(self, time_desc: str):
        """
        Initializes the Event with day, start time, and end time.

        Args:
            time_desc (str): Description of the event, e.g., "Monday 6:00pm - 7:30pm".
        """
        day, time_range = time_desc.split(" ", 1)
        self.day = day
        start, end = time_range.split(" - ")
        self.start_time = self._convert_to_minute(start)
        self.end_time = self._convert_to_minute(end)

    def _convert_to_minute(self, time_full: str):
        """
        Converts a time string to minutes since 12am.
        """
        period = time_full[-2:].lower()
        hour, minute = map(int, time_full[:-2].split(":"))

        if period == "am" and hour == 12:
            hour = 0
        elif period == "pm" and hour != 12:
            hour += 12
        return hour * 60 + minute

    def overlaps(self, other: "Event") -> bool:
        """
        Checks if this event overlaps with another event.
        """
        if self.day != other.day:
            return False
        return self.start_time < other.end_time and self.end_time > other.start_time

    def __repr__(self) -> str:
        """
        Return a string representation of the event.
        """
        def time_format(minutes: int) -> str:
            hours, mins = divmod(minutes, 60)
            return f"{hours:02}:{mins:02}"

        return f"{self.day[:3]} [{time_format(self.start_time)}-{time_format(self.end_time)}]"


class Course:
    """
    Represents a course with meeting times and related details.
    """

    def __init__(self, data: dict):
        """
        Initializes a Course object from a dictionary.
        """
        self.code = data['code']
        self.name = data['name']
        self.instructor = data['instructor']
        self.location = data['location']
        self.meeting_times = self.parse_meeting_times(data['meeting times'])

    def parse_meeting_times(self, meeting_times_str: str) -> list:
        """
        Parses meeting times string into Event objects.
        """
        return [Event(time_desc.strip()) for time_desc in meeting_times_str.split(';')]

    def overlaps(self, other: "Course") -> bool:
        """
        Checks if any meeting times overlap with another course.
        """
        return any(my_event.overlaps(other_event) for my_event in self.meeting_times for other_event in other.meeting_times)

    def __repr__(self) -> str:
        return f"{self.code}: {self.name}"


class Catalog:
    """
    Represents a catalog of courses.
    """

    def __init__(self, filename: str = "data/courses.csv"):
        """
        Initializes the Catalog by reading courses from a CSV file.
        """
        file_path = Path(__file__).parent / filename

        if not file_path.exists():
            raise FileNotFoundError(f"CSV file not found at: {file_path}")

        self.courses = []
        with file_path.open(newline='', mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                self.courses.append(Course(row))

    def search_by_schedule(self, schedule: list[Course]) -> list[Course]:
        """
        Returns a list of courses that do not overlap with any courses in the schedule.
        """
        return [course for course in self.courses if not any(course.overlaps(scheduled_course) for scheduled_course in schedule)]

    def search_by_code(self, prefix: str, schedule: list[Course] | None = None) -> list[Course]:
        """
        Returns a list of courses where the code starts with the given prefix.
        If schedule is set, conflicts should be omitted.
        """
        # Return non-conflicting courses first
        filtered_courses = self.search_by_schedule(schedule) if schedule else self.courses

        # Search for courses that contain the prefix
        matched_courses = [course for course in filtered_courses if prefix in course.code]

        return matched_courses

    def search_by_keyword(self, keyword: str, schedule: list[Course] | None = None) -> list[Course]:
        """
        Returns a list of courses where the name or instructor contains the keyword.
        If schedule is set, conflicts should be omitted.
        """
        keyword = keyword.lower()
        filtered_courses = self.search_by_schedule(schedule) if schedule else self.courses
        return [course for course in filtered_courses if keyword in course.name.lower() or keyword in course.instructor.lower()]
