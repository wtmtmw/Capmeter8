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
    const double threshold1 = 0.15;
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
        Cfind(diffabs, 1, threshold1, (L - 1), &indexpeak, &fc);
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
    const double threshold1 = 0.15;
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
        Cfind(diffabs, 1, threshold1, (L - 1), &indexpeak, &fc);
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

// int main() {
//     // Example of how to call the functions - for demonstration purposes
//     // You will need to replace this with actual input data as per your needs

//     // Define your input data here
//     double trigger[] = { /* Your trigger data */ };
//     double data[] = { /* Your data */ };
//     double time[] = { /* Your time data */ };
//     int L = /* Length of your data */;
//     double taufactor = /* Your taufactor */;
//     int endadj = /* Your endadj */;
//     int ppch = /* Points per channel */;
//     double ASYMP[ppch];
//     double PEAK[ppch];
//     double TAU[ppch];

//     // Call the function
//     SqCF(trigger, data, time, L, taufactor, endadj, ppch, ASYMP, PEAK, TAU);

//     // Print the results
//     for (int i = 0; i < ppch; i++) {
//         printf("ASYMP[%d]: %f, PEAK[%d]: %f, TAU[%d]: %f\n", i, ASYMP[i], i, PEAK[i], i, TAU[i]);
//     }

//     return 0;
// }