      SUBROUTINE TITLEJ(IPT,JPT)
C$$$  SUBPROGRAM DOCUMENTATION BLOCK
C                .      .    .                                       .
C SUBPROGRAM:    TITLEJ      PUT CUT OFF TIME IN TITLE
C   PRGMMR: LIN              ORG: W/NMC412   DATE: 97-02-10
C
C ABSTRACT: PLOTS DATA CUT OFF TIME OF ADPUPA ON 1-DOT AND 2-DOT
C   N. AMERICAN CHARTS.
C
C PROGRAM HISTORY LOG:
C   YY-MM-DD  ORIGINAL AUTHOR  UNKNOWN
C   88-07-25  GLORIA DENT  PUT IN DOCUMENTATION BLOCK
C   89-05-01  STEVE LILLY  UPDATE DOCUMENTATION BLOCK
C   93-05-03  LILLY CONVERT SUBROUTINE TO FORTRAN 77
C   97-02-10  LIN   CONVERT SUBROUTINE TO CFT     77
C
C USAGE:    CALL TITLEJ(IPT,JPT)
C
C   INPUT ARGUMENT LIST:
C     IPT      - THE I POSITION IN DOTS ON THE VARIAN
C     JPT      - THE J POSITION IN DOTS ON THE VARIAN
C
C   OUTPUT ARGUMENT LIST:
C     COMMON   - /TIMET/NANJK(2)
C
C REMARKS:
C
C ATTRIBUTES:
C   LANGUAGE: FORTRAN 77
C   MACHINE:  CRAY
C
C$$$
C
      COMMON /ADJUST/  IXADJ, IYADJ
C
      COMMON/TIMET/NANJK(2)
C     ...COMMON TIMET IS COMMON TO MAIN(PLOTOB) AND REDADP
      INTEGER   IPRIOR(2)
C
      XHT=1.0
      YHT=11.0
      IPRIOR(1)=0
      IPRIOR(2)=2
      IPT0 = IPT + IXADJ
      JPT0 = JPT + IYADJ
      IPT1=IPT0+130
C     CALL PUTLAB(IPT0,JPT0,XHT,'DATA CUT OFF ',0.0,13,IPRIOR,0)
C     CALL PUTLAB(IPT1,JPT0,YHT,NANJK(1),0.0,5,IPRIOR,0)
      RETURN
      END
