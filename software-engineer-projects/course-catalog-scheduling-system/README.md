# Course Catalog and Event Scheduling System 

### Overview 
The Course Catalog and Event Scheduling System is a Python-based application that allows users to search for courses, check schedule conflicts, and find available classes using a CSV file. 

### Features 
1. **Event Scheduling**: Parses meeting times and detects schedule conflicts.
2. **Course Management**: Handles course information, including code, instructor, and location.
3. **Search Capabilities**:
- Search for courses by code prefix.
- Search for courses by instructor or course name keyword.
- Find non-conflicting courses for a given schedule.

### Installation 
1. **Prerequisites**
- Python 3.7 or later
- A CSV file containing course information

2. **Set up** 
- Ensure you have a CSV file with the following required columns: 
    code,name,instructor,location,meeting times
- Example CSV data: 
    101,Introduction to Python,Dr. Smith,Room 101,Monday 6:00pm - 7:30pm; Wednesday 3:00pm - 4:30pm
    102,Data Structures,Dr. Johnson,Room 202,Tuesday 10:00am - 11:30am

### Usage 
1. **Creating an Event** 
```bash 
event1 = Event("Monday 6:00pm - 7:30pm")
event2 = Event("Monday 7:00pm - 8:30pm")
print(event1.overlaps(event2))  # Output: True
```

2. **Creating and Checking Course Overlaps** 
```bash 
course_data1 = {
    "code": "101",
    "name": "Python Programming",
    "instructor": "Dr. Smith",
    "location": "Room 101",
    "meeting times": "Monday 6:00pm - 7:30pm; Wednesday 3:00pm - 4:30pm"}

course_data2 = {
    "code": "102",
    "name": "Data Structures",
    "instructor": "Dr. Johnson",
    "location": "Room 202",
    "meeting times": "Monday 7:00pm - 8:30pm"}

course1 = Course(course_data1)
course2 = Course(course_data2)

print(course1.overlaps(course2))  # Output: True
```

3. **Loading the Course Catalog** 
```bash  
catalog = Catalog("courses.csv")
print(catalog.courses)  # Displays all courses from the CSV file
```

4. **Searching for Courses** 
- Find courses with a specific prefix 
```bash  
matching_courses = catalog.search_by_code("101")
print(matching_courses)  # Returns courses with codes starting with "101"
```
- Find courses by keyword (instructor or course name) 
```bash  
keyword_courses = catalog.search_by_keyword("Python")
print(keyword_courses)  # Returns all courses with "Python" in the name or instructor field
```
- Find non-conflicting courses
```bash  
my_schedule = [course1]  # Assume user is already enrolled in course1
available_courses = catalog.search_by_schedule(my_schedule)
print(available_courses)  # Returns courses that do not overlap with course1
```