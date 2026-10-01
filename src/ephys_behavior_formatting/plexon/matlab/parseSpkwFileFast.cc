// parseSpkWfile.cc - does a fast parse of the SPKW file


#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <sys/types.h>
#include <inttypes.h>
#include <string.h>
#include <mex.h>
#include "matrix.h"
#include "fileHeader.h"

#define int16 short
#define DEBUG_ON 1

struct waveFormHeader
{
    uint32 GPNumLSB;
    uint32 GPNumMSB;
    uint32 LPNumLSB;
    uint32 LPNumMSB;
    uint16 fragId;
    uint16 nFrag;
    uint32 GlobalClock;    
    
};

fileHeader fH;

#define MAXWF 10000 // 20000 ms of LFP data
#define NPOINTS 80

struct waveForm
{
    uint32 timeStamp;
    uint16 channelId;
    uint8 unit;
    uint8 dataLen;
    float sortInfo[3];
    int16 minW;
    int16 maxW;
    int16 waveForm[NPOINTS];
};

void mexFunction( int nlhs, mxArray *plhs[],
        int nrhs, const mxArray *prhs[] )
{

    FILE * pFile; // Create a file pointer
    
    char *fileName,*dataDir,*format, **fieldNames;
    char fullFileName[200];
    short int data[12];
    uint32 fSize, currLoc, bytesRead, headerBytes;
    uint16 nBytesOfWaveforms, nCurrentWaveforms, waveformId;
    uint32 TrialId;


    waveFormHeader wH;
    waveForm wF;
    
    
    
    
    mxArray *tmp;
    
    short *waveForms;
    short *nWaveForms;
    uint16 *channelIds;
    uint8 *units;
    uint32 *t,*cbTimeStamp;
    mwSize arraySize;
    
    
    // Error Checking
    if(nrhs < 3)
        mexErrMsgTxt(" MATLAB: parseContData:invalid Inputs, Need At Least 3 parameters, dataDir, fileName, Format");
    
    fileName = mxArrayToString(prhs[1]);
    dataDir = mxArrayToString(prhs[0]);
    format = mxArrayToString(prhs[2]);
    
    sprintf(fullFileName,"%s%s",dataDir,fileName);
    
    pFile = fopen ( fullFileName , "rb" );
    fSize = checkFile(pFile);
    
    
    if(strcmp(format,"BU001")==0)
    {
        bytesRead = fread(&fH,1,sizeof(fH),pFile);
        TrialId = fH.TrialId;
        #if DEBUG_ON
            printf("\n Header (%d bytes): %5d %s %s %s %d %s %10s", bytesRead, TrialId, fH.Type, fH.TaskName, fH.Version, fH.SaveTag, fH.CerebusId, fH.MonkeyName);
        #endif
    }
    

    waveformId = 1;
    bytesRead = fread(&wH,1,sizeof(wH),pFile);
    bytesRead =  fread(&nBytesOfWaveforms, 1, sizeof(nBytesOfWaveforms),pFile);
    nCurrentWaveforms = nBytesOfWaveforms/sizeof(wF);
    
    printf("\n waveform header size: %d, waveform size: %d, %d waveforms", sizeof(wH), sizeof(wF), nCurrentWaveforms);
    
    fclose(pFile);
}

