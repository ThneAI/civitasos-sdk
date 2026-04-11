"""CivitasOS Python Agent SDK — Package setup."""

from setuptools import setup, find_packages

setup(
    name="civitasos-sdk",
    version="1.0.0rc1",
    description="Python SDK for CivitasOS — the self-evolving AI society",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="ThneAI",
    author_email="thneonl@outlook.com",
    url="https://github.com/ThneAI/civitasos-sdk",
    license="MIT",
    python_requires=">=3.9",
    packages=["civitasos"],
    py_modules=["civitasos_sdk", "civitasos_client", "civitasos_cli"],
    install_requires=["PyNaCl>=1.5.0"],
    extras_require={
        "async": ["aiohttp>=3.9.0"],
    },
    entry_points={
        "console_scripts": [
            "civitasos=civitasos_cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
        "Topic :: System :: Distributed Computing",
    ],
)
