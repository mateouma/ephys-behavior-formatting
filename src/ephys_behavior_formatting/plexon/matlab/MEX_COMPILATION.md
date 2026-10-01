# MEX File Compilation Guide for parseContData

## Quick Compilation

### From MATLAB

```matlab
cd neuraldynamics/dataParsers
compile_mex
```

### From Command Line (macOS/Linux)

```bash
cd neuraldynamics/dataParsers
mex -v parseContData.cc
```

## Prerequisites

### All Platforms
- MATLAB R2020b or later (for Apple Silicon support)
- Configured C++ compiler

### macOS
- Xcode Command Line Tools
  ```bash
  xcode-select --install
  ```

### Linux
- GCC/G++ compiler
  ```bash
  sudo apt-get install build-essential
  ```

### Windows
- Microsoft Visual C++ (included with Visual Studio)
- Or MinGW-w64

## Configuration

First time setup - configure MATLAB's compiler:

```matlab
mex -setup C++
```

This will detect available compilers and let you select one.

## Expected Output Files

| Platform | Extension | Your System |
|----------|-----------|-------------|
| macOS (Intel) | `.mexmaci64` | ❌ |
| macOS (Apple Silicon) | `.mexmaca64` | ✅ (arm64) |
| Linux | `.mexa64` | ❌ |
| Windows | `.mexw64` | ❌ |

## Testing

After compilation, test the MEX function:

```matlab
base_dir = 'data/raw/plexon_test_files/20220311/';
file_id = 'Tiberius-CHKDLAY-CONT-63814366904-00000134.dat';
[cont, header] = parseContData(base_dir, file_id, 'BU001');

fprintf('Samples: %d\n', length(cont.t));
fprintf('SaveTag: %d\n', header.SaveTag);
```

## Troubleshooting

### "No supported compiler found"

**Solution:**
1. Install Xcode Command Line Tools (macOS):
   ```bash
   xcode-select --install
   ```

2. Configure MATLAB:
   ```matlab
   mex -setup C++
   ```

### "Undefined symbols for architecture arm64"

**Cause:** Trying to use Intel MEX file on Apple Silicon

**Solution:** Recompile for arm64:
```bash
mex -v parseContData.cc
```

### "parseContData not found" in Python

**Cause:** Wrong MEX extension for your architecture

**Solution:**
1. Check your architecture:
   ```bash
   uname -m  # Should show "arm64" on Apple Silicon
   ```

2. Check available MEX files:
   ```bash
   ls -la neuraldynamics/dataParsers/*.mex*
   ```

3. Compile for correct architecture (see above)

### Compilation warnings about types

The code uses older MATLAB type definitions (`UINT8_T`, etc.) which are compatible but may generate warnings. These are safe to ignore.

## Code Structure

```
parseContData.cc          # Main MEX implementation
fileHeader.h              # File header structure definition
headercheck.h             # Header validation utilities
```

### Key Data Structures

**`fileHeader` struct (56 bytes):**
- Type (5 chars)
- TaskName (8 chars)
- Version (6 chars)
- SaveTag (uint16)
- CerebusId (5 chars)
- TrialId (uint32)
- uniqueTrialId (double)
- MonkeyName (10 chars)

**`continuousData` struct (100 bytes):**
- GPNumLSB, GPNumMSB, LPNumLSB, LPNumMSB (uint32 × 4)
- fragNum, fragId (uint16 × 2)
- GlobalClock (double)
- Hand (double × 3)
- EyeFrameId (double)
- Eye (double × 2)
- PupilArea (double)
- Timestamp (double)
- PhotoBox (double)

## Performance

Expected performance on Apple M1/M2:
- Compilation time: ~1-2 seconds
- Parsing typical session (~3000 samples): ~0.01-0.05 seconds

## Alternative: Python/pybind11 Extension

If MEX compilation fails, use the Python C++ extension instead:

```bash
cd neuraldynamics/cpp
python setup.py build_ext --inplace
```

See `neuraldynamics/cpp/BUILD_INSTRUCTIONS.md` for details.

## Notes

- The MEX file is architecture-specific and not portable
- Each platform/architecture needs its own compiled version
- The `.cc` source code is portable and can be shared
- For version control: Commit `.cc` source, exclude `.mex*` binaries
