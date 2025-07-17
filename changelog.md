# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Performance logging to rocotostat.py to capture Rocoto response times and failure patterns
- Telescoping delay mechanism in attempt_multiple_times() function to reduce system load
- Comprehensive unit tests for the improved retry functionality
- Documentation on Rocoto thread usage and performance recommendations for HPC environments

### Changed
- Updated attempt_multiple_times() function to use exponential backoff instead of fixed delays
- Reduced base delay from 120s to 30s for faster initial response times
- Enhanced rocotostat.py with detailed performance monitoring and logging capabilities

### Fixed
- Reduced number of rocotostat calls to mitigate thread traffic in HPC environments
- Fixed variable scoping issue in exception handling for better error reporting
- Improved code formatting and style compliance with pycodestyle standards

### Technical Details
- Telescoping delay pattern: base_delay * (2^(attempt-1))
- Performance metrics logged: call_time, total_time, error details
- Four main rocotostat calls optimized with new retry logic
- Backward compatibility maintained with optional use_telescoping_delay parameter