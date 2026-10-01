function behavior = readBehavioralData(baseDir, fileId)
fid = fopen([baseDir fileId],'r');
rawData = fread(fid,'uint8');

behavior = [];
% Small bug in the parser that we don't have the
params = regexp(char(rawData)', '(<P>)(\w*):(\s*)(-*\d*\.?\d*)(\W*)(</P>)','tokens');

for paramId=1:length(params)
    currCell = params{paramId};
    behavior.(currCell{2}) = str2num(currCell{4});
end

fclose(fid);