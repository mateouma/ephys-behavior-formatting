typedef UINT8_T uint8;
typedef UINT16_T uint16;
typedef UINT32_T uint32;

#pragma pack(1)
// V016 onward included new code to include a monkey name in the R structs.
struct fileHeader // BU 001 well defined.
{
    char Type[5];
    char TaskName[8];
    char Version[6];
    uint16 SaveTag;
    char CerebusId[5];
    uint32 TrialId;
    double uniqueTrialId;
    char MonkeyName[10];
};


uint32 checkFile(FILE *pFile)
{
    uint32 fSize;
    if(pFile == NULL){
        mexErrMsgIdAndTxt( "MATLAB:parseContinuousMex:fileOpenFailed",
                "Could not open file, check filename \n");
    }
    fseek (pFile , 0 , SEEK_END);
    fSize = ftell(pFile);
    rewind(pFile);
    return fSize;
    
}
