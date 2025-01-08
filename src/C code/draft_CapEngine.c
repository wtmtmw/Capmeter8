#include <stdio.h>
#include <stdlib.h>
#include <math.h>

double Cabs(double data) {
    return (data < 0) ? -data : data;
}

void Cdiff(double *data, int size, double **A) {
    int i;
    *A = (double *)realloc(*A, (size - 1) * sizeof(double));
    for (i = 0; i < size - 1; i++) {
        (*A)[i] = data[i + 1] - data[i];
    }
}

void Cfind(double *data, int relation, double num, int size, int **A, int *fc) {
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

void Dfilter(double fcheck, double *data, int L, int filtered, int ppch, int M, double *output) {
    double *A = (double *)malloc(filtered * sizeof(double));
    for (int j = 0; j < ppch; j++) { //data point index
        if (fcheck) {
            for (int k = 0; k < filtered; k++) { //collect data to be averaged
                A[k] = data[j * L + k];
            }
            output[j] = Cmean(A, filtered);
        }
        else {
            output[j] = data[j * L];
        }
    }
    free(A);
}

void PSD(double *data, double *ref, int Mref, int L, int ppch, double *output) {
    double *A = (double *)malloc(Mref * sizeof(double));
    for (int i = 0; i < ppch; i++) {
        //i: data point index
        for (int j = 0; j < Mref; j++) {
            //for data*ref
            A[j] = data[(i * L) + j] * ref[j];
        }
        output[i] = 2 * Cmean(A, Mref);
    }
    free(A);
}

void SqCF(double *trigger, double *data, double *time, int L, double taufactor, int endadj, int ppch, double *ASYMP, double *PEAK, double *TAU) {
    const double threshold = 0.15;
    const int W = 25;
    double *dataA = (double *)malloc(L * sizeof(double)); //for each trigger
    double *dataTrig = (double *)malloc(L * sizeof(double));
    double *dataTime = (double *)malloc(L * sizeof(double));
    double *diffabs = (double *)malloc((L - 1) * sizeof(double));
    int *indexpeak = (int *)malloc(20 * sizeof(int));
    double *dataB = (double *)malloc(100 * sizeof(double)); //for each curve
    double *dataBtime = (double *)malloc(100 * sizeof(double));
    double *temp = (double *)malloc(L * sizeof(double));
    int *ftemp = (int *)malloc(L * sizeof(int));
    int n,i,fc,Sp;

    for (n = 0; n < ppch; n++) {
        //begin of the trigger loop(process every trigger)
        for (i = 0; i < L; i++) {
            dataA[i] = data[(n * L) + i];
            dataTrig[i] = trigger[(n * L) + i]; //trigger signal is from AI0
            dataTime[i] = time[(n * L) + i];
        }
        Cdiff(dataTrig, L, &diffabs); //TODO - consider removing the need of AI0 triger signal
        for (int i = 0; i < (L - 1); i++) {
            diffabs[i] = fabs(diffabs[i]);
        }
        Cfind(diffabs, 1, threshold, (L - 1), &indexpeak, &fc);
        if (fc != 0) {
            for (int i = 0; i < fc; i++) {
                indexpeak[i] += 1; //adjust the index
            }
        }
        Sp = fc - 1; //remove the last curve, bcz it's usually incomplete
        if (Sp < 1) {
            ASYMP[n] = NAN;
            PEAK[n] = NAN;
            TAU[n] = NAN;
            continue;
        }
        double zerosum = 0;
        for (int i = 0; i < (fc - fc % 2); i++) {
            zerosum += dataA[indexpeak[i]];
        }
        double zeroline = zerosum / (double)(fc - fc % 2);

        for (int i = 0; i < L; i++) {
            dataA[i] -= zeroline;
        }

        int validdata = 0;
        double asympaccu = 0, peakaccu = 0, tauaccu = 0;

        for (int np = 0; np < Sp; np++) {
            int SPC = indexpeak[np + 1] - indexpeak[np];
            if (SPC < 18) continue;

            dataB = (double *)realloc(dataB, SPC * sizeof(double));
            dataBtime = (double *)realloc(dataBtime, SPC * sizeof(double));
            double signB = Csign(Cmean(&dataA[indexpeak[np]], SPC));

            for (int i = 0; i < SPC; i++) {
                dataB[i] = dataA[indexpeak[np] + i] * signB;
                dataBtime[i] = dataTime[indexpeak[np] + i] - dataTime[indexpeak[np]];
            }

            int fc;
            Cfind(dataB, 0, Cmax(dataB, SPC), SPC, &ftemp, &fc);
            int lastmax = (fc != 0) ? ftemp[fc - 1] : 10;
            lastmax = (lastmax > SPC - 12) ? SPC - 12 : lastmax;

            int D = (int)floor((double)(SPC - lastmax) / 3);
            int sp1 = lastmax, sp2 = sp1 + D, sp3 = sp2 + D;
            int w = D;
            w = (sp3 + w > SPC) ? SPC - sp3 : w;

            double s1 = 0, s2 = 0, s3 = 0;
            for (int i = 0; i < w; i++) {
                s1 += dataB[sp1 + i];
                s2 += dataB[sp2 + i];
                s3 += dataB[sp3 + i];
            }
            s1 /= w; s2 /= w; s3 /= w;

            double asymp = (2 * s2 - s3 - s1 != 0) ? ((s2 * s2 - s1 * s3) / (2 * s2 - s3 - s1)) : 0;
            if (asymp == 0) continue;

            int firstmin = (taufactor < 0) ? SPC - 1 : Cpickend2(dataB, SPC, lastmax, taufactor) + endadj;
            firstmin = (firstmin <= lastmax) ? SPC - 1 : (firstmin < lastmax + 12) ? lastmax + 12 : firstmin;
            firstmin = (firstmin > SPC - 1) ? SPC - 1 : firstmin;

            for (int i = 0; i < SPC; i++) {
                dataB[i] -= asymp;
            }

            temp = (double *)realloc(temp, (firstmin - lastmax + 1) * sizeof(double));
            for (int i = 0; i < firstmin - lastmax + 1; i++) {
                temp[i] = dataB[lastmax + i];
            }
            Cfind(temp, -10, 0, firstmin - lastmax + 1, &ftemp, &fc);
            firstmin = (fc != 0) ? lastmax + ftemp[0] : firstmin;

            double sx = 0, sx2 = 0, sy = 0, sxy = 0;
            for (int i = 0; i < firstmin - lastmax + 1; i++) {
                double lny = log(dataB[lastmax + i]);
                sx += dataBtime[lastmax + i];
                sx2 += dataBtime[lastmax + i] * dataBtime[lastmax + i];
                sy += lny;
                sxy += dataBtime[lastmax + i] * lny;
            }
            double sxxsx = sx * sx;
            double fenmu = (double)(firstmin - lastmax + 1) * sx2 - sxxsx;
            if (fenmu != 0 && ((firstmin - lastmax + 1) * sxy - sx * sy) != 0) {
                double peak = exp(((sy * sx2 - sx * sxy) / fenmu)) + asymp;
                double tau = -1 / (((firstmin - lastmax + 1) * sxy - sx * sy) / fenmu);
                peakaccu += peak;
                tauaccu += tau;
                asympaccu += asymp;
                validdata++;
            }
        }

        if (validdata == 0) {
            ASYMP[n] = NAN;
            PEAK[n] = NAN;
            TAU[n] = NAN;
        } else {
            ASYMP[n] = asympaccu / validdata;
            PEAK[n] = peakaccu / validdata;
            TAU[n] = tauaccu / validdata;
        }
    }

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

void SqQ(double *trigger, double *data, double *time, int L, double taufactor, int endadj, int ppch, double interval, double *ASYMP, double *PEAK, double *TAU) {
    const double threshold = 0.15;
    const int W = 25;
    double *dataA = (double *)malloc(L * sizeof(double));
    double *dataTrig = (double *)malloc(L * sizeof(double));
    double *dataTime = (double *)malloc(L * sizeof(double));
    double *diffabs = (double *)malloc((L - 1) * sizeof(double));
    int *indexpeak = (int *)malloc(20 * sizeof(int));
    double *dataB = (double *)malloc(100 * sizeof(double));
    double *dataBtime = (double *)malloc(100 * sizeof(double));
    double *temp = (double *)malloc(L * sizeof(double));
    int *ftemp = (int *)malloc(L * sizeof(int));

    for (int n = 0; n < ppch; n++) {
        for (int i = 0; i < L; i++) {
            dataA[i] = data[n * (L + 1) + i];
            dataTrig[i] = trigger[n * (L + 1) + i];
            dataTime[i] = time[n * (L + 1) + i];
        }
        Cdiff(dataTrig, L, &diffabs);
        for (int i = 0; i < (L - 1); i++) {
            diffabs[i] = Cabs(diffabs[i]);
        }
        int fc;
        Cfind(diffabs, 1, threshold, (L - 1), &indexpeak, &fc);
        if (fc != 0) {
            for (int i = 0; i < fc; i++) {
                indexpeak[i] += 1;
            }
        }
        int Sp = fc - 1;
        if (Sp < 1) {
            ASYMP[n] = NAN;
            PEAK[n] = NAN;
            TAU[n] = NAN;
            continue;
        }
        double zerosum = 0;
        for (int i = 0; i < (fc - fc % 2); i++) {
            zerosum += dataA[indexpeak[i]];
        }
        double zeroline = zerosum / (double)(fc - fc % 2);

        for (int i = 0; i < L; i++) {
            dataA[i] -= zeroline;
        }

        int validdata = 0;
        double asympaccu = 0, peakaccu = 0, tauaccu = 0;

        for (int np = 0; np < Sp; np++) {
            int SPC = indexpeak[np + 1] - indexpeak[np];
            if (SPC < 18) continue;

            dataB = (double *)realloc(dataB, SPC * sizeof(double));
            dataBtime = (double *)realloc(dataBtime, SPC * sizeof(double));
            double signB = Csign(Cmean(&dataA[indexpeak[np]], SPC));

            for (int i = 0; i < SPC; i++) {
                dataB[i] = dataA[indexpeak[np] + i] * signB;
                dataBtime[i] = dataTime[indexpeak[np] + i] - dataTime[indexpeak[np]];
            }

            int fc;
            Cfind(dataB, 0, Cmax(dataB, SPC), SPC, &ftemp, &fc);
            int lastmax = (fc != 0) ? ftemp[fc - 1] : 5;
            lastmax = (lastmax > SPC - 12) ? SPC - 12 : lastmax;

            int D = (int)floor((double)(SPC - lastmax) / 3);
            int sp1 = lastmax, sp2 = sp1 + D, sp3 = sp2 + D;
            int w = (sp3 + D > SPC) ? SPC - sp3 : D;

            double s1 = 0, s2 = 0, s3 = 0;
            for (int i = 0; i < w; i++) {
                s1 += dataB[sp1 + i];
                s2 += dataB[sp2 + i];
                s3 += dataB[sp3 + i];
            }
            s1 /= w; s2 /= w; s3 /= w;

            double asymp = (2 * s2 - s3 - s1 != 0) ? ((s2 * s2 - s1 * s3) / (2 * s2 - s3 - s1)) : 0;
            if (asymp == 0) continue;

            dataB[0] = 0;
            for (int i = 1; i < SPC; i++) {
                dataB[i] = dataB[i - 1] + ((dataA[indexpeak[np] + i - 1] * signB - asymp) * interval);
            }

            s1 = 0; s2 = 0; s3 = 0;
            for (int i = 0; i < w; i++) {
                s1 += dataB[sp1 + i];
                s2 += dataB[sp2 + i];
                s3 += dataB[sp3 + i];
            }
            s1 /= w; s2 /= w; s3 /= w;
            double PeakTau = (2 * s2 - s3 - s1 != 0) ? ((s2 * s2 - s1 * s3) / (2 * s2 - s3 - s1)) : 0;
            if (PeakTau == 0) continue;

            for (int i = 0; i < SPC; i++) {
                dataB[i] = PeakTau - dataB[i];
            }

            Cfind(dataB, 0, Cmax(dataB, SPC), SPC, &ftemp, &fc);
            lastmax = (fc != 0) ? ftemp[fc - 1] : 2;
            lastmax = (lastmax > SPC - 12) ? SPC - 12 : lastmax;

            int firstmin = (taufactor < 0) ? SPC - 1 : Cpickend2(dataB, SPC, lastmax, taufactor) + endadj;
            firstmin = (firstmin <= lastmax) ? SPC - 1 : (firstmin < lastmax + 12) ? lastmax + 12 : firstmin;
            firstmin = (firstmin > SPC - 1) ? SPC - 1 : firstmin;

            temp = (double *)realloc(temp, (firstmin - lastmax + 1) * sizeof(double));
            for (int i = 0; i < firstmin - lastmax + 1; i++) {
                temp[i] = dataB[lastmax + i];
            }
            Cfind(temp, -10, 0, firstmin - lastmax + 1, &ftemp, &fc);
            firstmin = (fc != 0) ? lastmax + ftemp[0] : firstmin;

            double sx = 0, sx2 = 0, sy = 0, sxy = 0;
            for (int i = 0; i < firstmin - lastmax + 1; i++) {
                double lny = log(dataB[lastmax + i]);
                sx += dataBtime[lastmax + i];
                sx2 += dataBtime[lastmax + i] * dataBtime[lastmax + i];
                sy += lny;
                sxy += dataBtime[lastmax + i] * lny;
            }
            double sxxsx = sx * sx;
            double fenmu = (double)(firstmin - lastmax + 1) * sx2 - sxxsx;
            if (fenmu != 0 && ((firstmin - lastmax + 1) * sxy - sx * sy) != 0) {
                double tau = -1 / (((firstmin - lastmax + 1) * sxy - sx * sy) / fenmu);
                PeakTau *= (tau * (1 - exp(-interval / tau)) / interval);
                double peak = PeakTau / tau + asymp;
                asympaccu += asymp;
                peakaccu += peak;
                tauaccu += tau;
                validdata++;
            }
        }

        if (validdata == 0) {
            ASYMP[n] = NAN;
            PEAK[n] = NAN;
            TAU[n] = NAN;
        } else {
            ASYMP[n] = asympaccu / validdata;
            PEAK[n] = peakaccu / validdata;
            TAU[n] = tauaccu / validdata;
        }
    }

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

// void mexFunction(int nlhs, mxArray *plhs[],int nrhs, const mxArray *prhs[])
// {
//     int M,ppch,Mref;
//     double taufactor,endadj,*time,*trigger,*curr,*aich2,*TIME,*CURR,*AICH2,*ASYMP,*PEAK,*TAU; //for SqCF etc.
//     double *PSDref,*PSD90,*CAP,*COND; //for PSD
//     double fck3,fck4,filtered; //for Dfilter
//     double aiSamplesPerTrigger,algorism;
//     double interval;
    
//     if (nrhs == 0)
//     {
//         mexEvalString("disp('The program is under GNU GPLv3, see http://www.gnu.org/licenses for detail')");
//         plhs[0] = mxCreateString("CapEngine5-1.0");
//         return;
//     }
//     if(nrhs == 1)
//     {
//         mexEvalString("disp('CapEngine4(algo,time,current,AICH2,fck3,fck4,filtered,aiSamplesPerTrigger...)')");
//         algorism = mxGetScalar(prhs[0]);
//     }
//     else if((nrhs >= 10) && (nlhs >= 5))
//     {
//         algorism = mxGetScalar(prhs[0]);
//         M = mxGetM(prhs[1]);
//         //N = mxGetN(prhs[1]);
//         Mref = mxGetM(prhs[8]);
//         time = mxGetPr(prhs[1]);
//         curr = mxGetPr(prhs[2]);
//         aich2 = mxGetPr(prhs[3]);
//         fck3 = mxGetScalar(prhs[4]);
//         fck4 = mxGetScalar(prhs[5]);
//         filtered = mxGetScalar(prhs[6]);
//         aiSamplesPerTrigger = mxGetScalar(prhs[7]);
//         PSDref = mxGetPr(prhs[8]);
//         PSD90 = mxGetPr(prhs[9]);
//         ppch = (M+1)/(aiSamplesPerTrigger+1); //points per channel. +1 is the NaN
//         plhs[0] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         plhs[1] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         plhs[2] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         plhs[3] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         plhs[4] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         TIME = mxGetPr(plhs[0]);
//         CURR = mxGetPr(plhs[1]);
//         AICH2 = mxGetPr(plhs[2]);
//         CAP = mxGetPr(plhs[3]);
//         COND = mxGetPr(plhs[4]);
//         Dfilter(0,time,aiSamplesPerTrigger,filtered,ppch,TIME);
//         Dfilter(fck3,curr,aiSamplesPerTrigger,filtered,ppch,CURR);
//         Dfilter(fck4,aich2,aiSamplesPerTrigger,filtered,ppch,AICH2);
//     }
//     if(algorism == 1) {
//         if((nrhs != 10) || (nlhs != 5)) {mexErrMsgTxt("[time current AICH2 Cap Cond]=CapEngine4(1,time,current,AICH2,fck3,fck4,filtered,aiSamplesPerTrigger,PSDref,PSD90)");}
//     }
//     else if((algorism == 2)||(algorism == 3)) {
//         if((nrhs < 11) || (nrhs > 13) || (nlhs != 8)) mexErrMsgTxt("[time current AICH2 PSD90 PSD asymp peak tau]=CapEngine4(2or3,time,current,AICH2,fck3,fck4,filtered,aiSamplesPerTrigger,PSDref,PSD90,trigger,(opt)taufactor,(opt)endadj)");
//         trigger = mxGetPr(prhs[10]);
//         if(nrhs >= 12) {taufactor = 1/exp(mxGetScalar(prhs[11]));} //for firstmin
//         else {taufactor = -1;}
//         if(nrhs == 13) {endadj = mxGetScalar(prhs[12]);} //for firstmin
//         else {endadj = 0;} //default value
//         interval = (time[(int)(aiSamplesPerTrigger-1)]-time[0])/(aiSamplesPerTrigger-1);
//         //for unknown reasons, (int) has to be added here... (double) doesn't work...
        
//         plhs[5] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         plhs[6] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         plhs[7] = mxCreateDoubleMatrix(ppch,1,mxREAL);
//         ASYMP = mxGetPr(plhs[5]);
//         PEAK = mxGetPr(plhs[6]);
//         TAU = mxGetPr(plhs[7]);
//     }
//     else {mexErrMsgTxt("1:PSD 2:SQA-I 3:SQA-Q");}
//     if(algorism == 2) {SqCF(trigger,curr,time,aiSamplesPerTrigger,taufactor,endadj,ppch,ASYMP,PEAK,TAU);}
//     else if (algorism == 3) {
//         //SqQ(trigger,curr,time,aiSamplesPerTrigger,taufactor,endadj,ppch,ASYMP,PEAK,TAU);
//         SqQ(trigger,curr,time,aiSamplesPerTrigger,taufactor,endadj,ppch,interval,ASYMP,PEAK,TAU);
//     }
//     //also do PSD even the SQA is selected
//     PSD(curr,PSD90,Mref,aiSamplesPerTrigger,ppch,CAP);
//     PSD(curr,PSDref,Mref,aiSamplesPerTrigger,ppch,COND);
// }

//////////////////////////////////////////////////////////////////////////////////////
#include <math.h>
#include <stdlib.h>
#include <stdbool.h>
#include <float.h>

int compare(const void *a, const void *b) {
    double *p = (double *)a;
    double *q = (double *)b;
    if (*p > *q) return 1;
    else if (*p == *q) return 0;
    else return -1;
}

double getNaN() {
    return NAN;
}

void Rmean(double *A, int W, int M, bool *NaNindex, double *output) {
    double NaN = getNaN();
    double sum = 0;
    int count = W;

    for (int i = 0; i < M; i++) {
        if (i != 0) {
            if (!NaNindex[i - 1]) {
                sum -= A[i - 1];
                count--;
            }
            if (!NaNindex[i + W - 1]) {
                sum += A[i + W - 1];
                count++;
            }
        } else {
            for (int j = 0; j < W; j++) {
                if (NaNindex[j]) {
                    count--;
                } else {
                    sum += A[j];
                }
            }
        }
        if (count == 0) {
            output[i] = NaN;
            sum = 0;
        } else {
            output[i] = sum / count;
        }
    }
}

void Rmedian(double *A, int W, int M, bool *NaNindex, double *output) {
    double NaN = getNaN();
    double *B = (double *)malloc(W * sizeof(double));
    double *B0 = NULL;

    for (int i = 0; i < M; i++) {
        int indexR = -1, indexI = -2, count = 0;

        if (i != 0) {
            double nextpt = A[i + W - 1];

            if (NaNindex[i + W - 1]) {
                indexI = count - 1;
            }
            if (NaNindex[i - 1]) {
                indexR = count;
            }

            for (int j = 0; j < count; j++) {
                if ((indexI == -2) && (B[j] >= nextpt)) {
                    indexI = j - 1;
                }
                if ((indexR == -1) && (B[j] == A[i - 1])) {
                    indexR = j;
                }
                if ((indexI != -2) && (indexR != -1)) {
                    break;
                }
            }

            if (indexI == -2) {
                indexI = count - 1;
            }
            if (!NaNindex[i + W - 1]) {
                count++;
            }
            if (!NaNindex[i - 1]) {
                count--;
            }

            int cycle;
            if (indexI > indexR) {
                cycle = indexI - indexR;
                for (int j = 0; j < cycle; j++) {
                    B[indexR + j] = B[indexR + j + 1];
                }
                B[indexR + cycle] = nextpt;
            } else {
                cycle = indexR - indexI - 1;
                for (int j = 0; j < cycle; j++) {
                    B[indexR - j] = B[indexR - j - 1];
                }
                B[indexR - cycle] = nextpt;
            }
        } else {
            for (int j = 0; j < W; j++) {
                if (!NaNindex[j]) {
                    B[count++] = A[j];
                }
            }
            qsort(B, count, sizeof(double), compare);
        }

        if (count == 0) {
            output[i] = NaN;
        } else {
            if (count % 2 == 1) {
                output[i] = B[count / 2];
            } else {
                output[i] = (B[count / 2 - 1] + B[count / 2]) / 2;
            }
        }
    }

    free(B);
    if (B0) {
        free(B0);
    }
}

void Dfilter2(int fswitch, double *data, int W, int wswitch, int M, double *output) {
    double *A;
    bool *NaNindex;

    if (fswitch != 0) {
        A = (double *)malloc((M + W - 1) * sizeof(double));
        NaNindex = (bool *)malloc((M + W - 1) * sizeof(bool));

        int Lcat;
        if (wswitch == 1) {
            Lcat = W - 1;
        } else if (wswitch == -1) {
            Lcat = 0;
        } else {
            Lcat = (W % 2 == 0) ? W / 2 : (W - 1) / 2;
        }

        for (int i = 0; i < M + W - 1; i++) {
            if (i < Lcat) {
                A[i] = data[0];
            } else if (i >= M + Lcat) {
                A[i] = data[M - 1];
            } else {
                A[i] = data[i - Lcat];
            }
            NaNindex[i] = isnan(A[i]);
        }
    } else {
        for (int i = 0; i < M; i++) {
            output[i] = data[i];
        }
        return;
    }

    if (fswitch == 1) {
        Rmean(A, W, M, NaNindex, output);
    } else {
        Rmedian(A, W, M, NaNindex, output);
    }

    free(A);
    free(NaNindex);
}
// void mexFunction(int nlhs, mxArray *plhs[],int nrhs, const mxArray *prhs[])
// {
//     int M,N,fswitch,W;
//     int wswitch=0; //default
//     double *input,*output;
//     if (nrhs == 0)
//     {
//         //plhs[0] = mxCreateString("Dfilter2tmw060722");
//         mexEvalString("disp('YData=Dfilter2(fswitch,data,fwindow,wswitch)')");
//         mexEvalString("disp('fswitch 0:bypass,1:mean,2:median')");
//         mexEvalString("disp('wswitch -1:left,0:center,1:right')");
//         mexEvalString("disp('Developed by Tzu-Ming Wang. 070517')");
//         return;
//     }
//     if((nrhs!=3)&&(nrhs!=4)) mexErrMsgTxt("Dfilter2(fswitch,data,fwindow,wswitch)");
//     if(nlhs != 1) mexErrMsgTxt("YData=Dfilter2(...)");
//     M = mxGetM(prhs[1]);
//     N = mxGetN(prhs[1]);
//     fswitch = mxGetScalar(prhs[0]);
//     input = mxGetPr(prhs[1]);
//     W = mxGetScalar(prhs[2]);
//     if(nrhs == 4) {wswitch = mxGetScalar(prhs[3]);}
//     plhs[0] = mxCreateDoubleMatrix(M,N,mxREAL);
//     output = mxGetPr(plhs[0]);
//     Dfilter2(fswitch,input,W,wswitch,M,output);
// }
/////////////////////////////////////////////////////////////////////////////////////////
#include <math.h>
#include <stdlib.h>

void Cintspace(double v1, double v2, int pts, int *output) {
    int i;
    double linspace, intpart, floatpart;
    for (i = 0; i < pts; i++) {
        linspace = v1 + (i * (v2 - v1) / (pts - 1));
        floatpart = modf(linspace, &intpart);
        if (floatpart >= 0.5) intpart++;
        output[i] = (int)intpart;
    }
}

void DispCtrl(int M12, int set12, double *x12in, double *y1in, double *y2in, int M3, int set3, double *x3in, double *y3in, double *x12, double *y1, double *y2, double *x3, double *y3) {
    int i, *index12, *index3;

    if (M12 > set12) {
        index12 = (int *)malloc(set12 * sizeof(int));
        Cintspace(0, (M12 - 1), set12, index12);
        for (i = 0; i < set12; i++) {
            x12[i] = x12in[index12[i]];
            y1[i] = y1in[index12[i]];
            y2[i] = y2in[index12[i]];
        }
        free(index12);
    } else {
        for (i = 0; i < M12; i++) {
            x12[i] = x12in[i];
            y1[i] = y1in[i];
            y2[i] = y2in[i];
        }
    }

    if (M3 > set3) {
        index3 = (int *)malloc(set3 * sizeof(int));
        Cintspace(0, (M3 - 1), set3, index3);
        for (i = 0; i < set3; i++) {
            x3[i] = x3in[index3[i]];
            y3[i] = y3in[index3[i]];
        }
        free(index3);
    } else {
        for (i = 0; i < M3; i++) {
            x3[i] = x3in[i];
            y3[i] = y3in[i];
        }
    }
}
// void mexFunction(int nlhs, mxArray *plhs[],int nrhs, const mxArray *prhs[])
// {
//     int M12,M3,set12,set3,Mout12,Mout3;
//     double *X12in,*Y1in,*Y2in,*X3in,*Y3in;
//     double *X12,*Y1,*Y2,*X3,*Y3;
//     if (nrhs == 0)
//     {
//         mexEvalString("disp('[X12 Y1 Y2 X3 Y3] = DispCtrl(set12,X12,Y1,Y2,set3,X3,Y3)')");
//         return;
//     }
//     if(nrhs != 7) mexErrMsgTxt("DispCtrl(set12,X12,Y1,Y2,set3,X3,Y3)");
//     if(nlhs != 5) mexErrMsgTxt("[X12 Y1 Y2 X3 Y3] = DispCtrl(...)");
//     M12 = mxGetM(prhs[1]);
//     M3 = mxGetM(prhs[5]);
//     set12 = mxGetScalar(prhs[0]);
//     set3 = mxGetScalar(prhs[4]);
//     X12in = mxGetPr(prhs[1]);
//     Y1in = mxGetPr(prhs[2]);
//     Y2in = mxGetPr(prhs[3]);
//     X3in = mxGetPr(prhs[5]);
//     Y3in = mxGetPr(prhs[6]);
//     if(M12>set12) Mout12 = set12;
//     else Mout12 = M12;
//     if(M3>set3) Mout3 = set3;
//     else Mout3 = M3;
//     plhs[0] = mxCreateDoubleMatrix(Mout12,1,mxREAL);
//     plhs[1] = mxCreateDoubleMatrix(Mout12,1,mxREAL);
//     plhs[2] = mxCreateDoubleMatrix(Mout12,1,mxREAL);
//     plhs[3] = mxCreateDoubleMatrix(Mout3,1,mxREAL);
//     plhs[4] = mxCreateDoubleMatrix(Mout3,1,mxREAL);
//     X12 = mxGetPr(plhs[0]);
//     Y1 = mxGetPr(plhs[1]);
//     Y2 = mxGetPr(plhs[2]);
//     X3 = mxGetPr(plhs[3]);
//     Y3 = mxGetPr(plhs[4]);
//     DispCtrl(M12,set12,X12in,Y1in,Y2in,M3,set3,X3in,Y3in,X12,Y1,Y2,X3,Y3);
// //     DispCtrl(M12,set12,X12in,X12);
// }
//////////////////////////////////////////////////////////////////////////////////////////
#include <stdbool.h>

double Cabs(double data) {
    return (data < 0) ? -data : data;
}

void CrossCorr(double *SQA, double *PSD, double *R, int M) {
    int i;
    double *Tsqa = (double *)malloc(M * sizeof(double));
    double *Tpsd = (double *)malloc(M * sizeof(double));
    bool *nNaNindex = (bool *)malloc(M * sizeof(bool));
    int count = 0;
    double mx = 0, my = 0, sx2 = 0, sy2 = 0, sxy = 0;

    for (i = 0; i < M; i++) {
        Tsqa[i] = SQA[i];
        Tpsd[i] = PSD[i];
        nNaNindex[i] = !isnan(Tsqa[i]);
        my += Tpsd[i];
        if (nNaNindex[i]) {
            mx += Tsqa[i];
            count++;
        }
    }
    mx /= count;
    my /= M;

    for (i = 0; i < M; i++) {
        if (nNaNindex[i]) {
            Tsqa[i] -= mx;
            Tpsd[i] -= my;
            sx2 += Tsqa[i] * Tsqa[i];
            sy2 += Tpsd[i] * Tpsd[i];
            sxy += Tsqa[i] * Tpsd[i];
        }
    }
    *R = sxy / sqrt(sx2 * sy2);

    free(nNaNindex);
    free(Tsqa);
    free(Tpsd);
}

void PhaseScan(int tswitch, double *Csqa, double *Gsqa, double *Cpsd, double *Gpsd,
               double *PRmax, double *C_sft, double *G_sft, double *R_c, double *R_g,
               double startp, double endp, double pstep, int M, int cycle) {
    int i, j, Ccount1 = 0, Ccount2 = 0, count = 0;
    bool trend = false;
    double cosPS, sinPS, mx = 0, my = 0, sx2 = 0, sy2 = 0, sxy = 0;
    double Rnew, Rmax = -1;

    double *Tsqa = (double *)malloc(M * sizeof(double));
    double *Tpsd = (double *)malloc(M * sizeof(double));
    bool *nNaNindex = (bool *)malloc(M * sizeof(bool));

    for (i = 0; i < M; i++) {
        Tsqa[i] = tswitch ? Gsqa[i] : Csqa[i];
    }

    for (i = 0; i < M; i++) {
        nNaNindex[i] = !isnan(Tsqa[i]);
        if (nNaNindex[i]) {
            mx += Tsqa[i];
            count++;
        }
    }
    mx /= count;

    for (i = 0; i < M; i++) {
        if (nNaNindex[i]) {
            Tsqa[i] -= mx;
            sx2 += Tsqa[i] * Tsqa[i];
        }
    }

    for (j = 0; j < cycle; j++) {
        cosPS = cos(startp);
        sinPS = sin(startp);

        if (tswitch) {
            for (i = 0; i < M; i++) {
                Tpsd[i] = (Gpsd[i] * cosPS) + (Cpsd[i] * sinPS);
                my += Tpsd[i];
            }
        } else {
            for (i = 0; i < M; i++) {
                Tpsd[i] = (Cpsd[i] * cosPS) - (Gpsd[i] * sinPS);
                my += Tpsd[i];
            }
        }
        my /= M;

        for (i = 0; i < M; i++) {
            if (nNaNindex[i]) {
                Tpsd[i] -= my;
                sy2 += Tpsd[i] * Tpsd[i];
                sxy += Tsqa[i] * Tpsd[i];
            }
        }
        Rnew = sxy / sqrt(sx2 * sy2);

        if (Rnew > Rmax) {
            *PRmax = startp;
            Rmax = Rnew;
            if (tswitch) {
                *R_g = Rmax;
            } else {
                *R_c = Rmax;
            }
            Ccount1++;
            if (Ccount1 >= 3) trend = true;
        } else {
            Ccount1 = 0;
        }

        if (trend && (Rnew < Rmax)) {
            Ccount2++;
            if (Ccount2 >= 3) break;
        } else {
            Ccount2 = 0;
        }
        startp += pstep;
        my = sy2 = sxy = 0;
    }

    cosPS = cos(*PRmax);
    sinPS = sin(*PRmax);

    for (i = 0; i < M; i++) {
        C_sft[i] = (Cpsd[i] * cosPS) - (Gpsd[i] * sinPS);
        G_sft[i] = (Gpsd[i] * cosPS) + (Cpsd[i] * sinPS);
    }

    if (tswitch) {
        CrossCorr(Csqa, C_sft, R_c, M);
    } else {
        CrossCorr(Gsqa, G_sft, R_g, M);
    }

    free(nNaNindex);
    free(Tsqa);
    free(Tpsd);
}

void PhaseScan2(double *Csqa, double *Gsqa, double *Cpsd, double *Gpsd, double *PRmax,
                double *C_sft, double *G_sft, double *R_c, double *R_g,
                double startp, double endp, double pstep, int M, int cycle) {

    int i, j;

    // Variables for PhaseShift
    double *Tsqa, *Tsqa2; // Target-sqa, Csqa or Gsqa
    double *Tpsd, *Tpsd2; // Target-psd, phase-shifted Gpsd or Cpsd
    double cosPS, sinPS;

    // Variables for cross-correlation
    bool trend = false; // true if R increases
    const int consecpt = 5; // Examine 'consecpt' more points around Rmax
    int Ccount1 = 0, Ccount2 = 0; // Used with consecpt
    bool *nNaNindex, *nNaNindex2; // Not-NaN index
    int count = 0, count2 = 0; // Number of non-NaN points
    double mx = 0, my = 0, sx2 = 0, sy2 = 0, sxy = 0;
    double ma = 0, mb = 0, sa2 = 0, sb2 = 0, sab = 0;
    double Rs, Rc, Rg, Rmax = -2; // Rs = Rc + Rg

    // Allocate memory
    nNaNindex = (bool *)malloc(M * sizeof(bool));
    Tsqa = (double *)malloc(M * sizeof(double));
    Tpsd = (double *)malloc(M * sizeof(double));
    nNaNindex2 = (bool *)malloc(M * sizeof(bool));
    Tsqa2 = (double *)malloc(M * sizeof(double));
    Tpsd2 = (double *)malloc(M * sizeof(double));

    // Copy the variable
    for (i = 0; i < M; i++) {
        Tsqa[i] = Gsqa[i];
        Tsqa2[i] = Csqa[i];
    }

    // Identify non-NaN indices and compute means
    for (i = 0; i < M; i++) {
        nNaNindex[i] = !isnan(Tsqa[i]);
        nNaNindex2[i] = !isnan(Tsqa2[i]);

        if (nNaNindex[i]) {
            mx += Tsqa[i];
            count++;
        }
        if (nNaNindex2[i]) {
            ma += Tsqa2[i];
            count2++;
        }
    }
    mx /= count;
    ma /= count2;

    // Subtract means and compute variance
    for (i = 0; i < M; i++) {
        if (nNaNindex[i]) {
            Tsqa[i] -= mx;
            sx2 += Tsqa[i] * Tsqa[i];
        }
        if (nNaNindex2[i]) {
            Tsqa2[i] -= ma;
            sa2 += Tsqa2[i] * Tsqa2[i];
        }
    }

    // Scan the phase
    for (j = 0; j < cycle; j++) {
        cosPS = cos(startp);
        sinPS = sin(startp);

        for (i = 0; i < M; i++) {
            Tpsd[i] = (Gpsd[i] * cosPS) + (Cpsd[i] * sinPS);
            Tpsd2[i] = (Cpsd[i] * cosPS) - (Gpsd[i] * sinPS);
            my += Tpsd[i];
            mb += Tpsd2[i];
        }
        my /= M;
        mb /= M;

        for (i = 0; i < M; i++) {
            if (nNaNindex[i]) {
                Tpsd[i] -= my;
                sy2 += Tpsd[i] * Tpsd[i];
                sxy += Tsqa[i] * Tpsd[i];
            }
            if (nNaNindex2[i]) {
                Tpsd2[i] -= mb;
                sb2 += Tpsd2[i] * Tpsd2[i];
                sab += Tsqa2[i] * Tpsd2[i];
            }
        }

        Rg = sxy / sqrt(sx2 * sy2);
        Rc = sab / sqrt(sa2 * sb2);
        Rs = Rc + Rg;

        if (Rs > Rmax) {
            *PRmax = startp;
            Rmax = Rs;
            *R_g = Rg;
            *R_c = Rc;
            Ccount1++;

            if (Ccount1 >= consecpt) {
                trend = true;
            }
        } else {
            Ccount1 = 0;
        }

        if (trend && (Rs < Rmax)) {
            Ccount2++;
            if (Ccount2 >= consecpt) {
                break;
            }
        } else {
            Ccount2 = 0;
        }

        startp += pstep;
        my = mb = sy2 = sb2 = sxy = sab = 0;
    }

    // Calculate C_sft, G_sft at PRmax
    cosPS = cos(*PRmax);
    sinPS = sin(*PRmax);

    for (i = 0; i < M; i++) {
        C_sft[i] = (Cpsd[i] * cosPS) - (Gpsd[i] * sinPS);
        G_sft[i] = (Gpsd[i] * cosPS) + (Cpsd[i] * sinPS);
    }

    // Free allocated memory
    free(nNaNindex);
    free(Tsqa);
    free(Tpsd);
    free(nNaNindex2);
    free(Tsqa2);
    free(Tpsd2);
}

// void mexFunction(int nlhs, mxArray *plhs[],int nrhs, const mxArray *prhs[])
// {
//     int M,cycle,tswitch;
//     double *Csqa,*Gsqa,*Cpsd,*Gpsd;
//     double *P,*C_sft,*G_sft,*R_c,*R_g;
//     double startp,endp,pstep,pi;
//     pi = acos(-1);
// //     //for debug
// //     double *debugr,NaN;
// //     int dn = 270,i;
// //     NaN = mxGetNaN();
    
//     if(nrhs == 6)
//     {
//         if(nlhs != 5) {mexErrMsgTxt("[P,C_sft,G_sft,R_c,R_g] = PhaseMatcher2(switch,Csqa,Gsqa,Cpsd,Gpsd,step(degree))");}
//         M = mxGetM(prhs[1]);
//         tswitch = mxGetScalar(prhs[0]); //template switch. 0:Csqa, 1:Gsqa
//         Csqa = mxGetPr(prhs[1]);
//         Gsqa = mxGetPr(prhs[2]);
//         Cpsd = mxGetPr(prhs[3]);
//         Gpsd = mxGetPr(prhs[4]);
//         pstep = Cabs(mxGetScalar(prhs[5]));
//         startp = -180;
//         endp = 180;
//         cycle = (int)floor(endp-startp)/pstep;
//         startp *= pi/180;
//         endp *= pi/180;
//         pstep *= pi/180;
//         plhs[0] = mxCreateDoubleMatrix(1,1,mxREAL);
//         plhs[1] = mxCreateDoubleMatrix(M,1,mxREAL);
//         plhs[2] = mxCreateDoubleMatrix(M,1,mxREAL);
//         plhs[3] = mxCreateDoubleMatrix(1,1,mxREAL);
//         plhs[4] = mxCreateDoubleMatrix(1,1,mxREAL);
//         P = mxGetPr(plhs[0]);
//         C_sft = mxGetPr(plhs[1]);
//         G_sft = mxGetPr(plhs[2]);
//         R_c = mxGetPr(plhs[3]);
//         R_g = mxGetPr(plhs[4]);
//         if(tswitch < 0) {PhaseScan2(Csqa,Gsqa,Cpsd,Gpsd,P,C_sft,G_sft,R_c,R_g,startp,endp,pstep,M,cycle);}
//         else {PhaseScan(tswitch,Csqa,Gsqa,Cpsd,Gpsd,P,C_sft,G_sft,R_c,R_g,startp,endp,pstep,M,cycle);}
//         *P *= 180/pi;
//     }
//     else if(nrhs == 2)
//     {
//         if(nlhs != 1) {mexErrMsgTxt("R = PhaseMatcher2(traceSQA,tracePSD)");}
//         M = mxGetM(prhs[0]);
//         Csqa = mxGetPr(prhs[0]);
//         C_sft = mxGetPr(prhs[1]);
//         plhs[0] = mxCreateDoubleMatrix(1,1,mxREAL);
//         R_c = mxGetPr(plhs[0]);
//         CrossCorr(Csqa,C_sft,R_c,M);
//     }
//     else
//     {
//         mexEvalString("disp('[P,C_sft,G_sft,R_c,R_g] = PhaseMatcher2(switch,Csqa,Gsqa,Cpsd,Gpsd,step(degree))')");
//         mexEvalString("disp('switch 0:Csqa; 1:Gsqa; -1:C+G')");
//         mexEvalString("disp('or R = PhaseMatcher2(traceSQA,tracePSD)')");
//         mexEvalString("disp('Developed by Tzu-Ming Wang. 070619')");
//         return;
//     }
// }
////////////////////////////////////////////////////////////////////////////////////////
void SqWaveCalc(int nlhs, mxArray *plhs[],int nrhs, const mxArray *prhs[])
{
    int i,j,n;
    double L,N,A,*output;
    if (nrhs == 0)
    {
        plhs[0] = mxCreateString("SqWaveCalc060722tmw"); 
        return;
    }
    if(nrhs != 3) mexErrMsgTxt("SqWaveCalc(total samples,samples per wave,amplitude)");
    if(nlhs != 1) mexErrMsgTxt("wave=SqWaveCalc(...)");
    L = mxGetScalar(prhs[0]);
    N = mxGetScalar(prhs[1]);
    A = mxGetScalar(prhs[2]);
    n = (int)N;
    plhs[0] = mxCreateDoubleMatrix(L,1,mxREAL);
    output = mxGetPr(plhs[0]);
    for(i=0;i<(L/N);i++)
    {
        for(j=0;j<(N/2);j++) output[(i*n)+j] = A/2;
        for(j=N/2;j<N;j++) output[(i*n)+j] = -A/2;
    }
}