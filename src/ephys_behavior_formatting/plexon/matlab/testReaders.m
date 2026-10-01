baseDir = ['/media/rig1/data/Tiberius/May2021/20210514/'];
searchString = 'EVTS';
files = dir([baseDir '*-COLGRID*' searchString '-*.dat']);
versionId = 'BU001';

cnt = 1;
allTrials = [];
badTrials = [];
badTrials.BrokeTarget = 0;
badTrials.NoStart = 0;
badTrials.BrokeCenter = 0;
badTrials.nReset = 0;
badTrials.SaveTag = [];
badTrials.delayV = [];
for m=1:length(files)
    currFile = files(m).name;
    try
   
    evtsLoc = strfind(currFile, searchString);
    fileId = currFile;
    events = readEventData(baseDir, fileId);

    fileId = currFile;    
    fileId(evtsLoc:evtsLoc + length(searchString)-1) = 'BEHV';
    behavior = readBehavioralData(baseDir, fileId);
    
    fileId = currFile;
    fileId(evtsLoc:evtsLoc + length(searchString)-1) = 'CONT';
    [contdata,y] = parseContData(baseDir, fileId, 'BU001');
    
    switch(events.TrialOutcome)
        case {'Correct Choice','Wrong Choice'}
            allTrials(cnt).params = behavior;
            allTrials(cnt).events = events;
            allTrials(cnt).contBehavior = contdata;
            allTrials(cnt).TrialOutcome = events.TrialOutcome;
            allTrials(cnt).SaveTag = events.SaveTag;
            allTrials(cnt).TrialType = behavior.TrialType;
            allTrials(cnt).header.Task = events.Task;
            cnt = cnt + 1;
        case {'Broke Target'}
             badTrials.BrokeTarget = badTrials.BrokeTarget + 1;
     
        case {'No Initiate'}
            badTrials.NoStart = badTrials.NoStart + 1;
        case {'Broke Center'}
            badTrials.BrokeCenter = badTrials.BrokeCenter + 1;
            badTrials.delayV = [badTrials.delayV behavior.Delay];
            badTrials.SaveTag = [badTrials.SaveTag events.SaveTag];
    end
    catch
        
        currFile
    end
end


allOutcomes = {allTrials.TrialOutcome};
numNoInitate = length(strmatch('No Initiate',allOutcomes));
numCorrect = length(strmatch('Correct Choice',allOutcomes));
numInCorrect = length(strmatch('Wrong Choice',allOutcomes));

fprintf('\n Total Trials: %d', numCorrect + numInCorrect);
fprintf('\n Broke Center Holds: %d (%.2f%%)', badTrials.BrokeCenter, (badTrials.BrokeCenter/length(allTrials))*100);

%%

% sT = [allTrials.SaveTag];
% allTrials = allTrials(sT >=2);

allTrials = addPerformance(allTrials);
tcprintf('red','\n Red Left: %3.2f   ', Red_Left_Correct/(Red_Left_Correct + Red_Left_InCorrect));
tcprintf('red','Red Right: %3.2f', Red_Right_Correct/(Red_Right_Correct + Red_Right_InCorrect));

tcprintf('green','\n Green Left: %3.2f   ', Green_Left_Correct/(Green_Left_Correct + Green_Left_InCorrect));
tcprintf('green','Green Right: %3.2f', Green_Right_Correct/(Green_Right_Correct + Green_Right_InCorrect));
 
tcprintf('blue','\n Left Correct: %3.2f   ', (Red_Left_Correct + Green_Left_Correct)/((Red_Left_Correct + Green_Left_Correct) + (Red_Left_InCorrect + Green_Left_InCorrect)));
tcprintf('blue',' Right Correct: %3.2f', (Red_Right_Correct + Green_Right_Correct)/ ((Red_Right_Correct + Green_Right_Correct) + (Red_Right_InCorrect + Green_Right_InCorrect)));

tcprintf('red','\n Red Correct: %3.2f   ', (Red_Left_Correct + Red_Right_Correct)/((Red_Left_Correct + Red_Right_Correct) + (Red_Left_InCorrect + Red_Right_InCorrect)));
tcprintf('green',' Green Correct: %3.2f', (Green_Left_Correct + Green_Right_Correct)/ ((Green_Left_Correct + Green_Right_Correct) + (Green_Left_InCorrect + Green_Right_InCorrect)));        

tcprintf('magenta',sprintf('\n Overall correct : %3.2f', 100*sum(Dv(:,1))./size(Dv(:,1),1)));        


%%

plotPsychometricCurve(allTrials);


%%


cnt = 1;
D = [];
Delay = [];
for n=1:length(allTrials)
    switch(allTrials(n).TrialOutcome)
        case 'Correct Choice'
            D(cnt) = 1;
            Delay(cnt) = allTrials(n).params.Delay;
            cnt = cnt + 1;
        case 'Wrong Choice'
            D(cnt) = 0;
            Delay(cnt) = allTrials(n).params.Delay;
            cnt = cnt + 1;
            
    end
end

U = [linspace(min(Delay), max(Delay),15)];
V = [];
pDelay = [];
for b=1:length(U)-1
   ix = find(Delay > U(b) & Delay < U(b+1));
   Nt(b) = length(ix);
   V(b) = .5*(U(b) + U(b+1));
   pDelay(b) = nanmean(D(ix)); 
end

figure(3);
hold on;
plot(V, pDelay,'ro-');
