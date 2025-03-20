from catalog import Catalog

def main():
    # Load the catalog from the CSV file in the data folder
    catalog = Catalog("/Users/anitahuang/Anita-s-Portfolio/software-engineer-projects/Course Catalog and Scheduling System/data/courses.csv")

    # Example: Search for courses by keyword
    keyword = "Python"
    python_courses = catalog.search_by_keyword(keyword)
    print(f"\nCourses matching keyword '{keyword}':")
    for course in python_courses:
        print(course)

    # Example: Search for courses by code prefix
    prefix = "530"
    matched_courses = catalog.search_by_code(prefix)
    print(f"\nCourses with code prefix '{prefix}':")
    for course in matched_courses:
        print(course)

    # Example: Check for non-conflicting courses
    enrolled_course_codes = ["MPCS 53112-1", "MPCS 53014-1", "MPCS 51083-1"]
    my_schedule = [course for course in catalog.courses if course.code in enrolled_course_codes]
    available_courses = catalog.search_by_schedule(my_schedule)
    print("\nAvailable courses that do not conflict with your schedule:")
    for course in available_courses:
        print(course)

if __name__ == "__main__":
    main()
