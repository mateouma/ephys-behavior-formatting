% Compile MEX files for parseContData
% This script compiles the MEX file for the current architecture

fprintf('Compiling parseContData MEX file...\n');
fprintf('MATLAB version: %s\n', version);
fprintf('Architecture: %s\n', computer('arch'));

try
    % This is C++ code using old mexFunction API (separated complex)
    % MATLAB R2025b defaults to new interleaved complex C++ API
    % We need to explicitly use separated complex compilation

    % Create a custom options file or use direct compiler flags
    % The key is to avoid the new C++ MEX API symbols

    % Method: Compile object file manually, then link without C++ MEX symbols
    fprintf('Compiling object file...\n');

    % Compile to object file
    mex('-c', '-v', '-largeArrayDims', ...
        'CXXFLAGS=$CXXFLAGS -DMX_COMPAT_64', ...
        'parseContData.cc');

    % Link manually without C++ MEX API symbols
    fprintf('Linking MEX file...\n');
    if ismac
        % macOS linking command
        system(['/usr/bin/xcrun -sdk macosx clang++ -arch arm64 ' ...
                '-mmacosx-version-min=12.0 -bundle ' ...
                '-Wl,-exported_symbols_list,/Applications/MATLAB_R2025b.app/extern/lib/maca64/mexFunction.map ' ...
                'parseContData.o ' ...
                '-L/Applications/MATLAB_R2025b.app/bin/maca64 -lmx -lmex -lmat ' ...
                '-o parseContData.mexmaca64']);
    else
        error('Platform not supported by this script');
    end

    % Clean up object file
    if exist('parseContData.o', 'file')
        delete('parseContData.o');
    end

    fprintf('\n✓ Successfully compiled parseContData MEX file\n');

    % Check the output file
    if ismac
        if strcmp(computer('arch'), 'maca64')
            expected_file = 'parseContData.mexmaca64';
        else
            expected_file = 'parseContData.mexmaci64';
        end
    elseif isunix
        expected_file = 'parseContData.mexa64';
    elseif ispc
        expected_file = 'parseContData.mexw64';
    end

    if exist(expected_file, 'file')
        fprintf('✓ Output file: %s\n', expected_file);
    else
        fprintf('⚠ Warning: Expected file %s not found\n', expected_file);
        fprintf('  Available MEX files:\n');
        files = dir('parseContData.mex*');
        for i = 1:length(files)
            fprintf('    %s\n', files(i).name);
        end
    end

    % Test the compiled function
    fprintf('\nTesting compiled function...\n');
    test_file = '../../../data/raw/plexon_test_files/20220311/Tiberius-CHKDLAY-CONT-63814366904-00000134.dat';

    if exist(test_file, 'file')
        fprintf('Using test file: %s\n', test_file);
        [base_dir, file_id, ~] = fileparts(test_file);
        base_dir = [base_dir '/'];
        file_id = [file_id '.dat'];

        try
            [cont_data, header_data] = parseContData(base_dir, file_id, 'BU001');
            fprintf('✓ Successfully parsed test file\n');
            fprintf('  Number of samples: %d\n', length(cont_data.t));
            fprintf('  Header - SaveTag: %d, GlobalTrialId: %d\n', ...
                header_data.SaveTag, header_data.GlobalTrialId);
        catch ME
            fprintf('✗ Error testing MEX function: %s\n', ME.message);
        end
    else
        fprintf('⚠ Test file not found, skipping test\n');
    end

catch ME
    fprintf('\n✗ Compilation failed:\n');
    fprintf('  %s\n', ME.message);
    fprintf('\nTroubleshooting:\n');
    fprintf('  1. Make sure you have a C++ compiler configured\n');
    fprintf('  2. Run: mex -setup C++\n');
    fprintf('  3. On macOS, install Xcode Command Line Tools:\n');
    fprintf('     xcode-select --install\n');
end