function events = readEventData(baseDir, fileId)
fid = fopen([baseDir fileId],'r');
rawData = char(fread(fid,'uint8'));
fclose(fid);

hdrFrag = parseFileHeader(rawData);
events = [];
fN = fieldnames(hdrFrag);
for b=1:length(fN)
    events.(fN{b}) = hdrFrag.(fN{b});
end


eventData = regexp(char(rawData)', '(<E>)(\w*):(\s*)(-*\d*\.?\d*)(\W*)(</E>)','tokens');
for eventId=1:length(eventData)
    currCell = eventData{eventId};
    events.(currCell{2}) = str2num(currCell{4});
end

outcomeData = regexp(char(rawData)', '(<E>)(\s*)(outcome):([\w\s]*)(\0*)(</E>)','tokens');
events.TrialOutcome = outcomeData{1}{4};

