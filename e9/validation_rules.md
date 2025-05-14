# Validation Rules Documentation

## Overview
The validation system consists of three main components:
1. Input Validator
2. JSON Validator
3. Output Validator

Each validator is designed to ensure the safety, integrity, and appropriateness of data at different stages of processing.

## 1. Input Validator

### Purpose
Validates user input before processing to prevent security issues, inappropriate content, and ensure proper formatting.

### Validation Rules

#### 1.1 Code Injection Detection
- **Languages Monitored**: Python, SQL, JavaScript, Shell
- **Pattern Rules**:
  - Python: Detects import statements, function definitions, class definitions, etc.
  - SQL: Detects SELECT, INSERT, UPDATE, DELETE, and other SQL commands
  - JavaScript: Detects function declarations, variable declarations, etc.
  - Shell: Detects dangerous shell commands with flags
- **Whitelist Patterns**:
  - Allows common URL/file request patterns like "get from", "fetch from", "download from"
  - Ignores natural language usage of programming terms

#### 1.2 File Validation
- **Size Check**: Maximum file size limit (configurable, default: 5MB)
- **File Existence**: Verifies if referenced files exist
- **File Corruption**: Basic check for file readability
- **Supported Extensions**: .pdf, .txt, .doc, .docx, .json, .yaml, .yml, .py, .sql, .js

#### 1.3 URL Validation
- **Format Check**: Validates URL structure
- **Accessibility**: Basic URL format validation
- **Length Limit**: Maximum URL length of 2048 characters

#### 1.4 Content Filtering
- **Blocked Words**: Checks against a configurable list of blocked words
- **Sensitive Information**: Detects patterns like:
  - Passwords
  - API keys
  - Secrets
  - AWS keys
  - Private keys

#### 1.5 Query Length
- **Maximum Length**: Configurable (default: 1000 characters)
- **Empty Check**: Ensures query is not empty

## 2. JSON Validator

### Purpose
Ensures JSON responses are properly formatted and within acceptable limits.

### Validation Rules

#### 2.1 Structure Validation
- **Syntax Check**: Validates JSON syntax
- **Type Checking**: Ensures all values are of allowed types:
  - String
  - Integer
  - Float
  - Boolean
  - List
  - Dictionary
  - Null

#### 2.2 Size and Depth Limits
- **Maximum Size**: Configurable (default: 1024KB)
- **Maximum Depth**: Configurable (default: 10 levels)
- **Empty Check**: Ensures JSON is not empty

## 3. Output Validator

### Purpose
Validates the final output before returning to the user.

### Validation Rules

#### 3.1 Content Filtering
- **Blocked Words**: Same list as input validator
- **Inappropriate Content**: Checks for:
  - Offensive language
  - Sensitive information
  - Code snippets

#### 3.2 Format Validation
- **Type Check**: Ensures output is a string
- **Length Check**: Configurable maximum length

## Configuration

### Configuration File (profiles.yaml)
```yaml
validation:
  max_file_size_mb: 5
  max_query_length: 1000
  max_output_length: 10000
  max_json_size_kb: 1024
  max_json_depth: 10
  supported_languages:
    - python
    - sql
    - javascript
  allowed_json_types:
    - str
    - int
    - float
    - bool
    - list
    - dict
    - null
```

### Additional Configuration Files
1. **sensitive_patterns.txt**
   - Contains regex patterns for sensitive information detection
   - One pattern per line

2. **blocked_words.txt**
   - Contains list of blocked words
   - One word per line

## Error Handling

### Error Types
1. **Validation Errors**
   - Input validation failures
   - JSON validation failures
   - Output validation failures

2. **Configuration Errors**
   - Missing configuration files
   - Invalid configuration values

### Error Responses
- All validation errors return a tuple of (status, message)
- Status can be:
  - "process" or "dont_process" for input validation
  - True/False for JSON and output validation
- Messages are descriptive and include the specific validation failure

## Integration Points

### In Agent Loop
1. **Initial Input Validation**
   - Validates user input before processing
   - Returns error if validation fails

2. **JSON Response Validation**
   - Validates JSON responses from tools
   - Returns error if validation fails

3. **Final Output Validation**
   - Validates final answer before returning to user
   - Returns error if validation fails

## Best Practices

1. **Configuration Management**
   - Keep sensitive patterns and blocked words in separate files
   - Use configuration file for adjustable limits
   - Regular updates to blocked words and patterns

2. **Error Handling**
   - Log all validation failures
   - Provide clear error messages
   - Handle exceptions gracefully

3. **Performance**
   - Use efficient regex patterns
   - Cache configuration values
   - Minimize file I/O operations

4. **Security**
   - Regular updates to blocked words and patterns
   - Strict validation of file paths
   - Careful handling of sensitive information

## Future Improvements

1. **Enhanced Pattern Detection**
   - More sophisticated code injection detection
   - Better natural language understanding
   - Context-aware validation

2. **Performance Optimization**
   - Caching of validation results
   - Parallel validation where possible
   - Optimized regex patterns

3. **Additional Features**
   - Language-specific validation rules
   - Custom validation rules
   - Validation rule versioning