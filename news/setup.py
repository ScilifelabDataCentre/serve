from setuptools import setup

setup(
    name="studio-portal",
    version="0.0.1",
    description="""Django app for handling news in Serve""",
    url="https://www.scilifelab.se",
    include_package_data=True,
    package=["portal"],
    package_dir={"portal": "."},
    python_requires=">=3.6,<4",
    install_requires=[
        "django==4.2.5",
        "requests==2.31.0",
        "Pillow==9.4.0",
    ],
    license="Copyright Scaleout Systems AB. See license for details",
    zip_safe=False,
    keywords="",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)