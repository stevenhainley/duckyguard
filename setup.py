from setuptools import setup, find_packages

setup(
    name="duckyguard",
    version="2.2.0",
    author="Steven Hainley",
    description="Blocks keystroke-injection devices (Rubber Ducky, Flipper Zero) on macOS by typing rhythm",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/stevenhainley/DuckyGuard",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={"duckyguard": ["ui/*", "ui/fonts/*", "ui/icons/*", "data/*"]},
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Topic :: Security",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pynput>=1.8.0",
        "rumps>=0.4.0",
        "pyobjc-framework-Cocoa>=10",
        "pyobjc-framework-WebKit>=10",
        "pyobjc-framework-Quartz>=10",
    ],
    entry_points={"console_scripts": ["duckyguard=duckyguard.cli:main"]},
)
