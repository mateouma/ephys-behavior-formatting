function spikes = readRawLFPdata(baseDir, fileId)
%
% fields: 
%     lfp: lfp data: 32*timepoint
%     xPCtime: xPC time of each lfp data
%     CBfirstTime: first time point on cerebus that send lfp data packets
%     CBlastTime: last time point on cerebus that send lfp data packets
%     totalNumPackets: number of packets of each send, normally 4 (can be 2,6,8). 
%                       Note the data is int16 (2 byte). 4 means 2 int16 data in a packet
%


fid = fopen([baseDir fileId],'r');
rawData = fread(fid,'uint8');
[fileHeader,currPos] = parseFileHeader(rawData);
currPos = currPos-1;

rawData = uint8(rawData);

spikes = [];

AllData = [];

xPCtime = [];
CBfirstTime = [];
CBlastTime = [];
totalNumPackets = [];

while currPos < length(rawData)
    
%     try
    gpLSB = typecast(rawData(currPos+1:currPos+4),'uint32');
    gpMSB = typecast(rawData(currPos+5:currPos+8),'uint32');
    perLSB = typecast(rawData(currPos+5:currPos+8),'uint32');
    perMSB = typecast(rawData(currPos+5:currPos+8),'uint32');
    fragId = typecast(rawData(currPos+17:currPos+18),'uint16');
    nFrag = typecast(rawData(currPos+19:currPos+20),'uint16');
    xPCtimeStamp = typecast(rawData(currPos+21:currPos+28),'double');
    currPos = currPos + 28;

    %
    xPCtime = [xPCtime xPCtimeStamp];
    
    
    Data = [];
    for i=1:32
        
        currPos = currPos+3; % Skip the <D>
        
            
        firstCBtime = typecast(rawData(currPos+1:currPos+4),'uint32');
        currPos = currPos+4;
        lastCBtime = typecast(rawData(currPos+1:currPos+4),'uint32');
        currPos = currPos + 4;
        
        channelId(i) = rawData(currPos+1);
        currPos = currPos + 1;
        nChannels(i) = rawData(currPos+1);
        currPos = currPos + 1;
        numPackets(i) = rawData(currPos+1);
        currPos = currPos + 1;
        
        Data(channelId(i),:) = typecast(rawData(currPos+1:currPos+double(numPackets(i))),'int16')';
        currPos = currPos+double(numPackets(i));
        
        currPos = currPos+4;
        
    end
    
    AllData = [AllData Data];
    CBfirstTime = [CBfirstTime firstCBtime];
    CBlastTime = [CBlastTime, lastCBtime];
    totalNumPackets = [totalNumPackets, numPackets'];    
%     fprintf('\n %d',firstCBtime);
%     catch
%         keyboard
%     end
    
end

spikes.lfp = AllData;
fH = fieldnames(fileHeader);
for f=1:length(fH)
    spikes.(fH{f}) = fileHeader.(fH{f});
end

spikes.xPCtime = xPCtime;
spikes.CBfirstTime = CBfirstTime;
spikes.CBlastTime = CBlastTime;
spikes.totalNumPackets = totalNumPackets;

fclose(fid);