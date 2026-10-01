function [hdrFrag,currPos] = parseFileHeader(rawData)

header = {'Type','Task','Version','SaveTag','CerebusId','GlobalTrialId','UniqueId','MonkeyName'};
headerType = {'uint8','uint8','uint8','uint16','uint8','uint32','double','uint8'};
numValues = [5 8 6 2 5 4 8 10];

hdrFrag = [];
currPos = 1;
for varId=1:length(header)
    currValue = rawData(currPos:currPos + numValues(varId)-1);
    switch(headerType{varId})
        case 'uint8'
            if numValues(varId) > 1
                currValue = currValue(currValue > 0);
                hdrFrag.(header{varId}) = char(currValue)';
            else
                hdrFrag.(header{varId}) = currValue;
            end
        otherwise
            hdrFrag.(header{varId}) = typecast(uint8(currValue), headerType{varId});
    end
    currPos = currPos + numValues(varId);
end

