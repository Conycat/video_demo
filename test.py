import os

for root, dirs, files in os.walk('TEMP01'):
    for file in files:
        print(os.path.join(root, file))