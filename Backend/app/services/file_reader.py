from typing import List

def read_repository_files(file_paths: List[str]):

    repository_data = []

    # Visit every file one by one
    for file_path in file_paths:

        try:

           # Open the file safely Automatically close it afterwards.
            with open(file_path, "r", encoding="utf-8") as file:

                content = file.read()

                repository_data.append(
                    {
                        "path": file_path,
                        "content": content
                    }
                )

        except Exception as e:

            print(f"Could not read {file_path}: {e}")

    return repository_data