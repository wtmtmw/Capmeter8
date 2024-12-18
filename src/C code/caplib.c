#include <stdio.h>
#include <stdlib.h>
#include <math.h>

void Cdiff(double *data, int size, double **A) {
    int i;
    *A = (double *)realloc(*A, (size - 1) * sizeof(double));
    for (i = 0; i < size - 1; i++) {
        (*A)[i] = data[i + 1] - data[i];
    }
}

void Cfind(double *data, int relation, double num, int size, int **A, int *fc) {
    /*
    pass &(double *A) and &(int fc) to Cfind. return indexes(*A) and size(fc) of the index array
    After execution, *A points to an array containing the indices of all elements in data that 
    satisfy the specified relational condition.
    *fc contains the total number of such elements
    */
    int i, count = 0;
    for (i = 0; i < size; i++) {
        switch (relation) {
            case 1: if (data[i] > num) count++; break;
            case 10: if (data[i] >= num) count++; break;
            case 0: if (data[i] == num) count++; break;
            case -1: if (data[i] < num) count++; break;
            case -10: if (data[i] <= num) count++; break;
            default: break;
        }
    }
    *A = (int *)realloc(*A, count * sizeof(int));
    *fc = count;
    count = 0;
    for (i = 0; i < size; i++) {
        switch (relation) {
            case 1: if (data[i] > num) (*A)[count++] = i; break;
            case 10: if (data[i] >= num) (*A)[count++] = i; break;
            case 0: if (data[i] == num) (*A)[count++] = i; break;
            case -1: if (data[i] < num) (*A)[count++] = i; break;
            case -10: if (data[i] <= num) (*A)[count++] = i; break;
            default: break;
        }
    }
}

double Cmean(double *data, const int size) {
    double sum = 0;
    for (int i = 0; i < size; i++) {
        sum += data[i];
    }
    return sum / (double)size;  
}

double Cmax(double *data, int size) {
    double max = data[0];
    for (int i = 1; i < size; i++) {
        if (data[i] > max) max = data[i];
    }
    return max;
}

double Cmin(double *data, int size) {
    double min = data[0];
    for (int i = 1; i < size; i++) {
        if (data[i] < min) min = data[i];
    }
    return min;
}

int Cpickend2(double *data, int size, int lastmax, double taufactor) {
    int i = lastmax + 1;
    double target = data[lastmax] * taufactor; //target value, use peak to estimate dataB at tau*factor
    size = size - 1;
    while ((data[i] - target) > 0) {
        i++;
        if (i == size) break;
    }
    return i;
}

double Csign(double data) {
    return (data < 0) ? -1 : 1;
}

///////////////////////////////////////////
//Digital Filter///////////////////////////
///////////////////////////////////////////

void Dfilter(double fcheck, double *data, int L, int filtered, int ppch, double *output) {
    /*
    This is just an (not rolling) average filter.
    Input - data from one channel with size (samplesPerTrig)x(number of triggers)
    Output - filtered or downsampled data
    fcheck:     filter or not
    L:          aiSamplesPerTrigger
    filtered:   number of points to be filtered
    ppch:       points per channel after filter/downsampling
    output:     pre-allocated memory for storing the result
    */
    double *A = (double *)malloc(filtered * sizeof(double));
    for (int j = 0; j < ppch; j++) {
        //j: data point index
        if (fcheck) {
            for (int k = 0; k < filtered; k++) {
                //k: collect data to be averaged
                A[k] = data[j * L + k];
            }
            output[j] = Cmean(A, filtered);
        }
        else {
            output[j] = data[j * L];
        }
    }
    free(A);
    //TODO - consider allocating the memory within the fcn instead of outside
}

///////////////////////////////////////////
//Phase Sensitive Detector/////////////////
///////////////////////////////////////////

void PSD(double *data, double *ref, int Lref, int L, int ppch, double *output) {
    /*
    Input - current data with size (samplesPerTrig)x(number of triggers)
    Output - result based on the input reference wave
    ref:    reference wave
    Lref:   length of the reference wave
    L:      aiSamplesPerTrigger
    ppch:   points per channel after filter/downsampling
    output: pre-allocated memory for storing the result
    */
    double *A = (double *)malloc(Lref * sizeof(double));
    for (int i = 0; i < ppch; i++) {
        //i: data point index
        for (int j = 0; j < Lref; j++) {
            //for data*ref
            A[j] = data[(i * L) + j] * ref[j];
        }
        output[i] = 2 * Cmean(A, Lref);
    }
    free(A);
}

///////////////////////////////////////////
//real curve-fitting function starts here//
///////////////////////////////////////////

void SqCF(double *trigger,double *data,double *time,int L,double taufactor,int endadj,int ppch,double *ASYMP,double *PEAK,double *TAU) {
    int i;      //for the 'for' loop temporarily
    int n;      //the n-th of triggers
    int Sp;     //number of peaks
    int np;     //used with Sp
    int SPC;    //samples per curve
    const double threshold = 0.15; //for indexpeak
    
    //for asymptote calculation
    int sp1,sp2,sp3,D,firstmin,lastmax;
    const int W = 25;
    int w = W;
    double s1=0,s2=0,s3=0,zeroline,zerosum=0;
    
    //for linear regression etc
    int fladd1; //firstmin-lastmax+1
    double sx=0,sxxsx,sx2=0,sy=0,sxy=0,fenmu; //fenmu is the denominator
    
    //colletcing data etc
    int validdata = 0; //count valid data
    int quality = 1; //0 if there is NAN
    //const double taufactor = 3;
    double tau,peak,asymp,tauaccu=0,peakaccu=0,asympaccu=0;
    
    //dynamic varibles
    int fc; //counts of data found
    int *ftemp; //to store Cfind result
    int *indexpeak;
    double signB;
    double *dataA,*dataB,*dataTrig,*dataTime;
    double lny; //for linear regression
    double *diffabs,*dataBtime;
    double *temp;
    //1st used in Cdiff(dataB,SPC,&temp);
    //2nd used in (double *)realloc(temp,fladd1*sizeof(double));
    
    dataA = (double *)malloc(L * sizeof(double)); //for each trigger
    dataTrig = (double *)malloc(L * sizeof(double));
    dataTime = (double *)malloc(L * sizeof(double));
    diffabs = (double *)malloc((L - 1) * sizeof(double));
    indexpeak = (int *)malloc(20 * sizeof(int));
    dataB = (double *)malloc(100 * sizeof(double)); //for each curve
    dataBtime = (double *)malloc(100 * sizeof(double));
    temp = (double *)malloc(L * sizeof(double));
    ftemp = (int *)malloc(L * sizeof(int));

    for (n = 0; n < ppch; n++) {
        //begin of the trigger loop(process every trigger)
        for (i = 0; i < L; i++) {
            dataA[i] = data[(n * L) + i];
            dataTrig[i] = trigger[(n * L) + i]; //trigger signal is from AI0
            dataTime[i] = time[(n * L) + i];
        }
        Cdiff(dataTrig, L, &diffabs);
        for (i = 0; i < (L - 1); i++) {
            diffabs[i] = fabs(diffabs[i]);
        }
        Cfind(diffabs, 1, threshold, (L - 1), &indexpeak, &fc);
        if (fc != 0) {
            for (int i = 0; i < fc; i++) {
                indexpeak[i] += 1; //adjust the index
            }
        }
        
        Sp = fc-1; //remove the last curve, bcz it's usually incomplete
        if(Sp < 1) {
            quality = 0; //poor quality
        }
        
        if(quality) {
            for(i = 0; i < (fc - fmod(fc,2)); i++) {
                zerosum += dataA[(indexpeak[i])]; //sum of even number of peaks
            }
            zeroline = zerosum/(double)i; //middle/base line between up and down peak current
            
            for(i = 0; i < L; i++) {
                dataA[i] -= zeroline;
            }
            for(np = 0; np < Sp; np++) {
                //begin of the Sp loop(process every curve); np: n-th peak
                SPC = (indexpeak[np+1]-indexpeak[np]); //samples per curve
                if(SPC < 18) {
                    quality = 0;
                } //not a valid peak. bcz 100kHz/2.5kHz/2 = 20

                if(quality) {
                    dataB = (double *)realloc(dataB, SPC * sizeof(double));
                    dataBtime = (double *)realloc(dataBtime, SPC * sizeof(double));
                    signB = Csign(Cmean(&dataA[indexpeak[np]],SPC));
                    for(i = 0; i < SPC; i++) {
                        dataB[i] = dataA[(indexpeak[np]+i)]*signB; //assign data and correct the polarity
                        dataBtime[i] = dataTime[(indexpeak[np]+i)]-dataTime[indexpeak[np]]; //set initial time to 0
                    }
                    //get lastmax
                    Cfind(dataB,0,Cmax(dataB,SPC),SPC,&ftemp,&fc);
                    if(fc != 0) {lastmax = ftemp[(fc-1)];} //fc-1 is the last one.
                    else {lastmax = 10;}
                    if(lastmax > (SPC-12)) {lastmax = SPC-12;}
                    
                    //get firstmin later. use the last point(SPC-1) to estimate asymp
                    //so that Ch2 noise will be much smaller
                    D = (int)floor((double)(SPC-lastmax)/3);
                    w = D;
                    //if(w > D) {w = D;}
                    sp1 = lastmax;
                    sp2 = sp1+D;
                    sp3 = sp2+D;
                    
                    if((sp3+w) > SPC) {w = SPC-sp3;}
                    
                    for(i = 0; i < w; i++) {
                        s1 += dataB[(sp1+i)];
                        s2 += dataB[(sp2+i)];
                        s3 += dataB[(sp3+i)];
                    }
                    s1 /= w;
                    s2 /= w;
                    s3 /= w;
                    
                    //get asymptote
                    if((2*s2-s3-s1) != 0) {
                        asymp = (((s2*s2)-(s1*s3))/(2*s2-s3-s1));
                    }
                    else {
                        quality = 0;
                    }
                }
                
                if(quality) {
                    //proceed if asymp is valid
                    //get firstmin
                    if(taufactor < 0) {firstmin = SPC-1;}
                    else {
                        firstmin = Cpickend2(dataB, SPC, lastmax, taufactor) + endadj; //adj the range
                    }
                    if(firstmin <= lastmax) {firstmin = SPC-1;}
                    else if(firstmin < (lastmax+12)) {firstmin = lastmax+12;}
                    if(firstmin > (SPC-1)) {firstmin = SPC-1;}
                    fladd1 = (firstmin-lastmax+1);
                    
                    for(i = 0; i < SPC; i++) {dataB[i] -= asymp;} //It is ln(current data - baseline)
                    temp = (double *)realloc(temp,fladd1*sizeof(double));
                    for(i = 0; i < fladd1; i++) {temp[i] = dataB[(lastmax+i)];}
                    Cfind(temp, -10, 0, fladd1, &ftemp, &fc);
                    if(fc != 0) {firstmin = lastmax + ftemp[0];} //so that there won't be negative # in log
                    //                 for(i=0;i<1;i++) {debugr[i] = lastmax;} /////////////////////for debug
                    //                 return; ///////////////////////for debug
                    
                    //linear regression
                    fladd1 = (firstmin-lastmax+1);
                    for(i = 0; i < fladd1; i++) {
                        lny = log(dataB[(lastmax+i)]);
                        sx += dataBtime[(lastmax+i)];
                        sx2 += (dataBtime[(lastmax+i)]*dataBtime[(lastmax+i)]);
                        sy += lny;
                        sxy += (dataBtime[(lastmax+i)]*lny);
                    }
                    sxxsx = sx*sx;
                    fenmu = ((double)fladd1)*sx2-sxxsx;
                    if((fenmu != 0)&&(((fladd1*sxy)-(sx*sy)) != 0)) {
                        //get peak and tau
                        peak = exp((((sy*sx2)-(sx*sxy))/fenmu))+asymp;
                        tau = -1/(((fladd1*sxy)-(sx*sy))/fenmu);
                    }
                    else {quality = 0;}
                    //for(i=0;i<1;i++) {debugr[i] = tau;} /////////////////////for debug
                }

                if(quality) {
                    asympaccu += asymp;
                    peakaccu += peak;
                    tauaccu += tau;
                    validdata++;
                }
                w = W;
                s1 = 0;
                s2 = 0;
                s3 = 0;
                sx = 0;
                sx2 = 0;
                sy = 0;
                sxy = 0;
                sxxsx = 0;
                quality = 1;
            } //end of the Sp loop
        }
        if(validdata == 0) {
            ASYMP[n] = NAN;
            PEAK[n] = NAN;
            TAU[n] = NAN;
        }
        else {
            ASYMP[n] = asympaccu/validdata;
            PEAK[n] = peakaccu/validdata;
            TAU[n] = tauaccu/validdata;
        }
        asympaccu = 0;
        peakaccu = 0;
        tauaccu = 0;
        validdata = 0;
        zerosum = 0;
    }//end of trigger loop
    free(dataA);
    free(dataTrig);
    free(dataTime);
    free(diffabs);
    free(indexpeak);
    free(dataB);
    free(dataBtime);
    free(temp);
    free(ftemp);
}

///////////////////////////////////////////
//charge integration starts here///////////
///////////////////////////////////////////

void SqQ(double *trigger,double *data,double *time,int L,double taufactor,int endadj,int ppch,double interval,double *ASYMP,double *PEAK,double *TAU) {
    //int db; //for debug
    int i; //for the 'for' loop temporarily
    int n; //the n-th of triggers
    int Sp; //number of peaks
    int np; //used with Sp
    int SPC; //samples per curve
    double PeakTau; //peak*tau (asymp-subtracted peak)
    const double threshold = 0.15; //for indexpeak
    
    //for asymptote calculation
    int sp1,sp2,sp3,D,firstmin,lastmax;
    const int W = 25;
    int w = W;
    double s1,s2,s3,zeroline,zerosum=0;
    
    //for linear regression etc
    int fladd1; //firstmin-lastmax+1
    double sx=0,sxxsx,sx2=0,sy=0,sxy=0,fenmu; //fenmu is the denominator
    
    //colletcing data etc
    int validdata = 0; //count valid data
    int quality = 1; //0 if there is NAN
    double tau,peak,asymp,tauaccu=0,peakaccu=0,asympaccu=0;
    
    //dynamic varibles
    int fc; //counts of data found
    int *ftemp; //to store Cfind result
    int *indexpeak;
    double signB;
    double *dataA,*dataB,*dataTrig,*dataTime;
    double lny; //for linear regression
    double *diffabs,*dataBtime;
    double *temp;
    //1st used in Cdiff(dataB,SPC,&temp);
    //2nd used in (double *)realloc(temp,fladd1*sizeof(double));
    
    dataA = (double *)malloc(L * sizeof(double)); //for each trigger
    dataTrig = (double *)malloc(L * sizeof(double));
    dataTime = (double *)malloc(L * sizeof(double));
    diffabs = (double *)malloc((L - 1) * sizeof(double));
    indexpeak = (int *)malloc(20 * sizeof(int));
    dataB = (double *)malloc(100 * sizeof(double)); //for each curve's Q
    dataBtime = (double *)malloc(100 * sizeof(double));
    temp = (double *)malloc(L * sizeof(double));
    ftemp = (int *)malloc(L * sizeof(int));
    
    for (n = 0; n < ppch; n++) {
        //begin of the trigger loop(process every trigger)
        for (i = 0; i < L; i++) {
            dataA[i] = data[(n * L) + i];
            dataTrig[i] = trigger[(n * L) + i]; //trigger signal is from AI0
            dataTime[i] = time[(n * L) + i];
        }
        Cdiff(dataTrig, L, &diffabs);
        for (i = 0; i < (L - 1); i++) {
            diffabs[i] = fabs(diffabs[i]);
        }
        Cfind(diffabs, 1, threshold, (L - 1), &indexpeak, &fc);
        if (fc != 0) {
            for (int i = 0; i < fc; i++) {
                indexpeak[i] += 1; //adjust the index
            }
        }
        
        Sp = fc-1; //remove the last curve, bcz it's usually incomplete
        if(Sp < 1) {
            quality = 0; //poor quality
        }

        if(quality) {
            for(i = 0; i < (fc - fmod(fc,2)); i++) {
                zerosum += dataA[(indexpeak[i])]; //sum of even number of peaks
            }
            zeroline = zerosum/(double)i; //middle/base line between up and down peak current
            
            for(i = 0; i < L; i++) {
                dataA[i] -= zeroline;
            }
            for(np = 0; np < Sp; np++) {
                //begin of the Sp loop(process every curve); np: n-th peak
                SPC = (indexpeak[np+1]-indexpeak[np]); //samples per curve
                if(SPC < 18) {
                    quality = 0;
                } //not a valid peak. bcz 100kHz/2.5kHz/2 = 20

                 if(quality) {
                    dataB = (double *)realloc(dataB, SPC * sizeof(double));
                    dataBtime = (double *)realloc(dataBtime, SPC * sizeof(double));
                    signB = Csign(Cmean(&dataA[indexpeak[np]],SPC));
                    for(i = 0; i < SPC; i++) {
                        dataB[i] = dataA[(indexpeak[np]+i)]*signB; //assign data and correct the polarity
                        dataBtime[i] = dataTime[(indexpeak[np]+i)]-dataTime[indexpeak[np]]; //set initial time to 0
                    }
                    //get lastmax
                    Cfind(dataB,0,Cmax(dataB,SPC),SPC,&ftemp,&fc);
                    if(fc != 0) {lastmax = ftemp[(fc-1)];} //fc-1 is the last one.
                    else {lastmax = 5;}
                    if(lastmax > (SPC-12)) {lastmax = SPC-12;}
                    
                    //get firstmin later. use the last point(SPC-1) to estimate asymp
                    //so that Ch2 noise will be much smaller
                    D = (int)floor((double)(SPC-lastmax)/3);
                    w = D;
                    //if(w > D) {w = D;}
                    sp1 = lastmax;
                    sp2 = sp1+D;
                    sp3 = sp2+D;
                    if((sp3+w) > SPC) {w = SPC-sp3;}
                    s1=0;s2=0;s3=0;
                    for(i=0;i<w;i++)
                    {
                        s1 += dataB[(sp1+i)];
                        s2 += dataB[(sp2+i)];
                        s3 += dataB[(sp3+i)];
                    }
                    s1 /= w;
                    s2 /= w;
                    s3 /= w;
                    
                    //get asymptote
                    if((2*s2-s3-s1) != 0) {
                        asymp = (((s2*s2)-(s1*s3))/(2*s2-s3-s1));
                    }
                    else {
                        quality = 0;
                    }                    
                    //Note: getting asymp from Q is worse than getting from I directly
                }
                
                if(quality) {
                    //proceed if asymp is valid
                    dataB[0] = 0;
                    for(i = 1; i < SPC; i++) {
                        //notice that i starts at 1
                        dataB[i] = dataB[i-1]+((dataA[(indexpeak[np]+i-1)]*signB-asymp)*interval); //Qs=int((I-asymp)*dt)
                    }
                    
                    //estimate peak*tau from Q-subtracted (dataB)
                    s1=0;s2=0;s3=0;
                    for(i = 0; i < w; i++) {
                        s1 += dataB[(sp1+i)];
                        s2 += dataB[(sp2+i)];
                        s3 += dataB[(sp3+i)];
                    }
                    s1 /= w;
                    s2 /= w;
                    s3 /= w;
                    if((2*s2-s3-s1) != 0) {
                        PeakTau = (((s2*s2)-(s1*s3))/(2*s2-s3-s1));
                    }
                    else {
                        quality = 0;
                    }
                    
                    if(quality) {
                        //Reverse the Q-subtracted curve for fitting
                        for(i = 0; i < SPC; i++) {dataB[i] = PeakTau-dataB[i];}
                        //for(db=0;db<SPC;db++) {debuger[db] = dataB[db];} /////////////////////for debug
                        //adjust lastmax again
                        Cfind(dataB,0,Cmax(dataB,SPC),SPC,&ftemp,&fc);
                        if(fc != 0) {lastmax = ftemp[(fc-1)];} //fc-1 is the last one.
                        else {lastmax = 2;}
                        if(lastmax > (SPC-12)) {lastmax = SPC-12;}

                        //get firstmin
                        if(taufactor < 0) {
                            firstmin = SPC-1;
                        }
                        else {
                            firstmin = Cpickend2(dataB,SPC,lastmax,taufactor)+endadj; //adj the range
                            //firstmin = Cpickend(dataB,SPC,SPC)+endadj; //maximal consecutive pt
                        }
                        if(firstmin <= lastmax) {firstmin = SPC-1;}
                        else if(firstmin < (lastmax+12)) {firstmin = lastmax+12;}
                        if(firstmin > (SPC-1)) {firstmin = SPC-1;}
                        //for(db=0;db<1;db++) {debuger[0] = lastmax;debuger[1] = firstmin;} /////////////////////for debug
                        fladd1 = (firstmin-lastmax+1);
                        
                        temp = (double *)realloc(temp,fladd1*sizeof(double));
                        for(i = 0; i < fladd1; i++) {temp[i] = dataB[(lastmax+i)];}
                        Cfind(temp,-10,0,fladd1,&ftemp,&fc);
                        if(fc != 0) {firstmin = lastmax+ftemp[0];} //so that there won't be negative # in log
                        
                        //linear regression
                        fladd1 = (firstmin-lastmax+1);
                        for(i = 0; i < fladd1; i++) {
                            lny = log(dataB[(lastmax+i)]);
                            sx += dataBtime[(lastmax+i)];
                            sx2 += (dataBtime[(lastmax+i)]*dataBtime[(lastmax+i)]);
                            sy += lny;
                            sxy += (dataBtime[(lastmax+i)]*lny);
                        }
                        sxxsx = sx*sx;
                        fenmu = ((double)fladd1)*sx2-sxxsx;
                        //for(db=0;db<1;db++) {debuger[0] = PeakTau;debuger[1] = -1/(((fladd1*sxy)-(sx*sy))/fenmu);} /////////////////////for debug
                        if((fenmu != 0)&&(((fladd1*sxy)-(sx*sy)) != 0)) {
                            //get peak and tau
                            tau = -1/(((fladd1*sxy)-(sx*sy))/fenmu);
                            PeakTau *= (tau*(1-exp(-interval/tau))/interval); //correct int(Q)
                            peak = PeakTau/tau+asymp;
                        }
                        else {quality = 0;}
//                         for(db=0;db<1;db++) {debuger[0] = asymp;debuger[1] = peak;debuger[2] = tau;/////////////////////for debug
//                         debuger[3] = lastmax;debuger[4] = firstmin;} /////////////////////for debug
                    }
                }

                if(quality) {
                    asympaccu += asymp;
                    peakaccu += peak;
                    tauaccu += tau;
                    validdata++;
                }
                w = W;
                s1 = 0;
                s2 = 0;
                s3 = 0;
                sx = 0;
                sx2 = 0;
                sy = 0;
                sxy = 0;
                sxxsx = 0;
                quality = 1;
            } //end of the Sp loop
        }
        if(validdata == 0) {
            ASYMP[n] = NAN;
            PEAK[n] = NAN;
            TAU[n] = NAN;
        }
        else {
            ASYMP[n] = asympaccu/validdata;
            PEAK[n] = peakaccu/validdata;
            TAU[n] = tauaccu/validdata;
        }
        asympaccu = 0;
        peakaccu = 0;
        tauaccu = 0;
        validdata = 0;
        zerosum = 0;
    }//end of trigger loop
    free(dataA);
    free(dataTrig);
    free(dataTime);
    free(diffabs);
    free(indexpeak);
    free(dataB);
    free(dataBtime);
    free(temp);
    free(ftemp);
}
    
//todo
void mexFunction(int nlhs, mxArray *plhs[],int nrhs, const mxArray *prhs[])
{
    int M,ppch,Mref;
    double taufactor,endadj,*time,*trigger,*curr,*aich2,*TIME,*CURR,*AICH2,*ASYMP,*PEAK,*TAU; //for SqCF etc.
    double *PSDref,*PSD90,*CAP,*COND; //for PSD
    double fck3,fck4,filtered; //for Dfilter
    double aiSamplesPerTrigger,algorism;
    double interval;
    
    if (nrhs == 0)
    {
        mexEvalString("disp('The program is under GNU GPLv3, see http://www.gnu.org/licenses for detail')");
        plhs[0] = mxCreateString("CapEngine5-1.0");
        return;
    }
    if(nrhs == 1)
    {
        mexEvalString("disp('CapEngine4(algo,time,current,AICH2,fck3,fck4,filtered,aiSamplesPerTrigger...)')");
        algorism = mxGetScalar(prhs[0]);
    }
    else if((nrhs >= 10) && (nlhs >= 5))
    {
        algorism = mxGetScalar(prhs[0]);
        M = mxGetM(prhs[1]);
        //N = mxGetN(prhs[1]);
        Mref = mxGetM(prhs[8]);
        time = mxGetPr(prhs[1]);
        curr = mxGetPr(prhs[2]);
        aich2 = mxGetPr(prhs[3]);
        fck3 = mxGetScalar(prhs[4]);
        fck4 = mxGetScalar(prhs[5]);
        filtered = mxGetScalar(prhs[6]);
        aiSamplesPerTrigger = mxGetScalar(prhs[7]);
        PSDref = mxGetPr(prhs[8]);
        PSD90 = mxGetPr(prhs[9]);
        ppch = (M+1)/(aiSamplesPerTrigger+1); //points per channel. +1 is the NaN
        plhs[0] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        plhs[1] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        plhs[2] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        plhs[3] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        plhs[4] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        TIME = mxGetPr(plhs[0]);
        CURR = mxGetPr(plhs[1]);
        AICH2 = mxGetPr(plhs[2]);
        CAP = mxGetPr(plhs[3]);
        COND = mxGetPr(plhs[4]);
        Dfilter(0,time,aiSamplesPerTrigger,filtered,ppch,TIME);
        Dfilter(fck3,curr,aiSamplesPerTrigger,filtered,ppch,CURR);
        Dfilter(fck4,aich2,aiSamplesPerTrigger,filtered,ppch,AICH2);
    }
    if(algorism == 1) {
        if((nrhs != 10) || (nlhs != 5)) {mexErrMsgTxt("[time current AICH2 Cap Cond]=CapEngine4(1,time,current,AICH2,fck3,fck4,filtered,aiSamplesPerTrigger,PSDref,PSD90)");}
    }
    else if((algorism == 2)||(algorism == 3)) {
        if((nrhs < 11) || (nrhs > 13) || (nlhs != 8)) mexErrMsgTxt("[time current AICH2 PSD90 PSD asymp peak tau]=CapEngine4(2or3,time,current,AICH2,fck3,fck4,filtered,aiSamplesPerTrigger,PSDref,PSD90,trigger,(opt)taufactor,(opt)endadj)");
        trigger = mxGetPr(prhs[10]);
        if(nrhs >= 12) {taufactor = 1/exp(mxGetScalar(prhs[11]));} //for firstmin
        else {taufactor = -1;}
        if(nrhs == 13) {endadj = mxGetScalar(prhs[12]);} //for firstmin
        else {endadj = 0;} //default value
        interval = (time[(int)(aiSamplesPerTrigger-1)]-time[0])/(aiSamplesPerTrigger-1);
        //for unknown reasons, (int) has to be added here... (double) doesn't work...
        
        plhs[5] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        plhs[6] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        plhs[7] = mxCreateDoubleMatrix(ppch,1,mxREAL);
        ASYMP = mxGetPr(plhs[5]);
        PEAK = mxGetPr(plhs[6]);
        TAU = mxGetPr(plhs[7]);
    }
    else {mexErrMsgTxt("1:PSD 2:SQA-I 3:SQA-Q");}
    if(algorism == 2) {SqCF(trigger,curr,time,aiSamplesPerTrigger,taufactor,endadj,ppch,ASYMP,PEAK,TAU);}
    else if (algorism == 3) {
        //SqQ(trigger,curr,time,aiSamplesPerTrigger,taufactor,endadj,ppch,ASYMP,PEAK,TAU);
        SqQ(trigger,curr,time,aiSamplesPerTrigger,taufactor,endadj,ppch,interval,ASYMP,PEAK,TAU);
    }
    //also do PSD even the SQA is selected
    PSD(curr,PSD90,Mref,aiSamplesPerTrigger,ppch,CAP);
    PSD(curr,PSDref,Mref,aiSamplesPerTrigger,ppch,COND);
}

