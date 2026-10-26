from setuptools import setup, find_packages

setup(
    name="duckyguard",
    version="1.0.0",
    author="Steven Hainley",
    description="Autonomous Endpoint Defense Against HID Injection & BadUSB Attacks",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/stevenhainley/DuckyGuard",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Topic :: Security",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pynput>=1.7.6",
        "rumps>=0.4.0",
    ],
    entry_points={
        "console_scripts": [
            "duckyguard=duckyguard.cli:main",
        ],
    },
)
