function spikes = readSpikeWaveforms(baseDir, fileId)
%
%
%
fid = fopen([baseDir fileId],'r');
rawData = fread(fid,'uint8');
[fileHeader,currPos] = parseFileHeader(rawData);
currPos = currPos-1;

SPIKEPACKETSIZE = 80*2+24;

rawData = uint8(rawData);

spikes = [];
spikeCnt = 1;

while currPos < length(rawData)
    try
        
        gpLSB = typecast(rawData(currPos+1:currPos+4),'uint32');
        gpMSB = typecast(rawData(currPos+5:currPos+8),'uint32');
        perLSB = typecast(rawData(currPos+5:currPos+8),'uint32');
        perMSB = typecast(rawData(currPos+5:currPos+8),'uint32');
        fragId = typecast(rawData(currPos+17:currPos+18),'uint16');
        nFrag = typecast(rawData(currPos+19:currPos+20),'uint16');
        xPCtimeStamp = typecast(rawData(currPos+21:currPos+28),'double');
        currPos = currPos + 28;
        
        dataSize = typecast(rawData(currPos+1:currPos+2),'uint16');
        currPos = currPos + 2;
        nSpikes = dataSize/SPIKEPACKETSIZE;
    
       
        for f=1:nSpikes
            
            spikes.xPCtimeStamp(spikeCnt) = xPCtimeStamp;
            
            spikes.CBtimeStamp(spikeCnt) = typecast(rawData(currPos+1:currPos+4),'uint32');
            currPos = currPos + 4;
            spikes.channelId(spikeCnt) = typecast(rawData(currPos+1:currPos+2),'uint16');
            currPos = currPos + 2;
            spikes.unit(spikeCnt) = rawData(currPos+1);
            currPos = currPos + 1;
            spikes.numData(spikeCnt) = rawData(currPos+1);
            currPos = currPos + 1;
            
            currPos = currPos + 16;
            
            spikes.data(spikeCnt,:) = typecast(rawData(currPos+1:currPos + 80*2),'int16');
            currPos = currPos + 160;
            
            
            spikeCnt = spikeCnt + 1;
        end
        
        
    catch err
        rethrow(err)  % was `keyboard`, which hangs when called through the MATLAB engine
    end
end

fH = fieldnames(fileHeader);
for f=1:length(fH)
    spikes.(fH{f}) = fileHeader.(fH{f});
end


fclose(fid);