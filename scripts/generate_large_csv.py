import csv
import os
import random

def generate_large_csv(filepath: str, num_rows: int = 10000):
    departments = ["Sales", "Billing", "HR", "Engineering", "Marketing", "Support"]
    cities = ["Chennai", "Coimbatore", "Madurai", "Salem", "Trichy", "Bangalore"]
    first_names = ["Arun", "Priya", "Kumar", "Meena", "Rahul", "Sonia", "Vikram", "Kavitha", "Deepak", "Anitha"]
    last_names = ["Kumar", "Sharma", "Patel", "Singh", "Rao", "Nair", "Iyer", "Reddy", "Verma", "Gupta"]

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["EmpID", "Name", "Department", "Salary", "City"])
        
        for i in range(1, num_rows + 1):
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            dept = random.choice(departments)
            salary = random.randint(25000, 120000)
            city = random.choice(cities)
            writer.writerow([f"EMP{i:05d}", name, dept, salary, city])

    print(f"Successfully generated {num_rows} rows in {filepath}")

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(__file__), "..", "sample-data", "large_test.csv")
    generate_large_csv(os.path.abspath(target), 10000)
