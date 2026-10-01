#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <sys/types.h>
#include <inttypes.h>
#include <string.h>
#include <mex.h>
#include "matrix.h"
#include "fileHeader.h"

// NFields is defined by fileHeader.h
// over-write NFields in this script
#define NFields 10
#define NUMHEADERS 3
#define DEBUG_ON 0

struct continuousData
{
    uint32 GPNumLSB;
    uint32 GPNumMSB;
    uint32 LPNumLSB;
    uint32 LPNumMSB;
    uint16 fragNum;
    uint16 fragId;
    double GlobalClock;

    double Hand[3];
    double EyeFrameId;
    double Eye[2];
    double PupilArea;
    double Timestamp; 
    double PhotoBox;
};
// BU001


fileHeader fH;

int writtenBytes = sizeof(continuousData); //120; // uint32 is 4 bytes each, char is 1 byte each, double is 8 bytes each
char **getFieldNames()
{
    // Create a two Dimensional array of field names 7x20. Its a double pointer
    char **fieldNames;
    fieldNames = new char*[NFields]; // MW, was 7 // now 11 as of 2017-01-24 see fileHeader.h
    for(int k=0;k < NFields;++k)
    {
        fieldNames[k] = new char[20];
    }
    strcpy(fieldNames[0],"t");
    strcpy(fieldNames[1],"HandX");
    strcpy(fieldNames[2],"HandY");
    strcpy(fieldNames[3],"HandZ");
    strcpy(fieldNames[4],"FrameId");
    strcpy(fieldNames[5],"EyeX");
    strcpy(fieldNames[6],"EyeY");
    strcpy(fieldNames[7],"PupilArea");
    strcpy(fieldNames[8],"timeStamp"); // MW
    strcpy(fieldNames[9],"PhotoBox"); // MW
    

    return fieldNames;
}


char **getHeaderNames()
{
    char **headerNames;
    headerNames = new char*[4]; // MW, was 7 // now 11 as of 2017-01-24 see fileHeader.h
    for(int k=0;k < NUMHEADERS;++k)
    {
        headerNames[k] = new char[20];
    }
    strcpy(headerNames[0],"SaveTag");
    strcpy(headerNames[1],"UniqueTrialId");
    strcpy(headerNames[2],"GlobalTrialId");
    

    return headerNames;
}

void mexFunction( int nlhs, mxArray *plhs[],
        int nrhs, const mxArray *prhs[] )
{

    FILE * pFile; // Create a file pointer

    char *fileName,*dataDir,*format, **fieldNames, **headerNames;
    continuousData cD;
    char fullFileName[200];
    uint32 fSize, currLoc, TrialId, bytesRead;


    mxArray *tmp[NFields],*fout; // MW, was 7
    double *data[NFields]; // MW, was 7

    mxArray *hdrData[NUMHEADERS];

        int i = 0;
    int numSamples = 0;
    int moveForward = 1;


    // Error Checking

    if(nrhs < 3) // number right hand side
        mexErrMsgTxt(" MATLAB: parseContData:invalid Inputs, Need At Least 3 parameters, dataDir, fileName, Format");


    fileName = mxArrayToString(prhs[1]);
    dataDir = mxArrayToString(prhs[0]);
    format = mxArrayToString(prhs[2]);

    sprintf(fullFileName,"%s%s",dataDir,fileName);

    mxCreateNumericMatrix(numSamples+1,1,mxDOUBLE_CLASS,mxREAL);
    pFile = fopen ( fullFileName , "rb" );
    if(pFile == NULL){
        mexErrMsgIdAndTxt( "MATLAB:parseContinuousMex:fileOpenFailed",
                "Could not open file, check filename \n");
    }


    // Get the size of the file and then return it.
    fseek (pFile , 0 , SEEK_END);
    fSize = ftell(pFile);
    rewind(pFile);

    

    if(strcmp(format,"BU001")==0)
    {
        bytesRead = fread(&fH,1,sizeof(fH),pFile);
        numSamples = (fSize - sizeof(fH))/sizeof(struct continuousData);
        TrialId = fH.TrialId;
        #if DEBUG_ON
            printf("\n %s %s %s %d %s ", fH.Type, fH.TaskName, fH.Version, fH.SaveTag, fH.CerebusId);
        #endif
    }
    if(moveForward)
    {

        fieldNames = getFieldNames();
        headerNames = getHeaderNames();
        plhs[0] = mxCreateStructMatrix(1,1, NFields, (const char **) fieldNames);
        plhs[1] = mxCreateStructMatrix(1,1, NUMHEADERS, (const char **) headerNames);
        
        hdrData[0] = mxCreateDoubleScalar(fH.SaveTag);
        hdrData[1] = mxCreateDoubleScalar(fH.TrialId);
        hdrData[2] = mxCreateDoubleScalar(fH.uniqueTrialId);
        for(int nH=0; nH < NUMHEADERS; nH++)
        {
            mxSetFieldByNumber(plhs[1],0,nH,hdrData[nH]);
        }

        for(int k=0; k < NFields;++k) // MW, was k < 7
        {
            tmp[k] = mxCreateNumericMatrix(numSamples+1,1,mxDOUBLE_CLASS,mxREAL);
            data[k] = mxGetPr(tmp[k]);
        }




        while(!feof(pFile))
        {
            bytesRead = fread(&cD,sizeof(cD),1,pFile);
            data[0][i] = cD.GlobalClock;
            data[1][i] = cD.Hand[0];
            data[2][i] = cD.Hand[1];
            data[3][i] = cD.Hand[2];
            data[4][i] = cD.EyeFrameId;
            data[5][i] = cD.Eye[0];
            data[6][i] = cD.Eye[1];
            data[7][i] = cD.PupilArea;
            data[8][i] = cD.Timestamp;
            data[9][i] = cD.PhotoBox;
            i++;
        }

        for(int k=0; k < NFields;++k) // MW, was k < 7
        {
            mxSetFieldByNumber(plhs[0],0,k,tmp[k]);
        }

    
        #if DEBUG_ON
                printf("\n Num Samples:%d \n Num Bytes: %d \n TrialId: %d, Bytes Read:%d \n ", numSamples, fSize, TrialId, bytesRead);
                mexPrintf("\n So Far So Good");
        #endif

        

    }
    fclose(pFile);
}

