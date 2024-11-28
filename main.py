import os
import re

def is_costas_array(array):
    n = len(array)
    
    # Convert array to coordinates
    dots = [(i, array[i]) for i in range(n)]
    
    # Check if each row and column has exactly one dot
    rows = set(x for x, _ in dots)
    cols = set(y for _, y in dots)
    if len(rows) != n or len(cols) != n:
        return False
    
    # Check for unique vectors between all pairs of dots
    vectors = set()
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dx = j - i
            dy = array[j] - array[i]
            vector = (dx, dy)
            if vector in vectors:
                return False
            vectors.add(vector)
    
    return True

def generate_test_arrays(n):
    """Read arrays of dimension n from the corresponding file.
    
    Args:
        n (int): Dimension of Costas arrays to read
        
    Yields:
        list[int]: Valid Costas arrays of dimension n
        
    Raises:
        FileNotFoundError: If the corresponding data file is not found
    """
    filename = f"db/Costas_essense_N={n}.txt"
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and "No Costas arrays" marker
                if not line or line == "No Costas arrays.":
                    continue
                    
                try:
                    array = [int(x) for x in line.split()]
                    # Validate array dimension
                    if len(array) == n:
                        yield array
                except ValueError:
                    # Skip lines that can't be parsed as integers
                    continue
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return []  # Return empty iterator when file not found

def test_dimension(n):
    """Test various arrays of dimension n"""
    found_costas = False
    
    for arr in generate_test_arrays(n):
        if is_costas_array(arr):
            found_costas = True
            print(f"Found Costas array of dimension {n}: {arr}")
    
    if not found_costas:
        print(f"No Costas arrays found for dimension {n}")

def main():
    # Get all files in the db directory
    db_dir = "db"
    for filename in os.listdir(db_dir):
        if filename.startswith("Costas_essense_N="):
            # Extract N from filename using regex
            match = re.search(r'N=(\d+)', filename)
            if match:
                n = int(match.group(1))
                print(f"\nTesting dimension N={n}")
                test_dimension(n)

if __name__ == "__main__":
    main()
