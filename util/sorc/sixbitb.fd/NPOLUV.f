      SUBROUTINE NPOLUV(FULOLA,FVLOLA,IMAX,JMAX,IEXIT)
C$$$  SUBPROGRAM DOCUMENTATION BLOCK
C
C SUBPROGRAM: NPOLUV         CORRECT N. POLE ROW U-& V-COMPONENTS LOLA
C   PRGMMR: KUMAR            ORG: NP/12    DATE: 1999-12-21
C
C ABSTRACT: CORRECTS NORTH POLE ROW OF U- & V-COMPONENTS OF WIND IN
C   THE LONGITUDE/LATITUDE (LOLA) GRID FIELDS.  AN AVERAGE WIND IS
C   DETERMINED FROM THE ROW ADJACENT TO THE NORTH POLE ROW, THEN THAT
C   AVERAGE WIND IS STORED IN THE POLE ROW AFTER ROTATION OF AXIS
C   TO EACH MERIDIAN.
C
C PROGRAM HISTORY LOG:
C   82-04-23  SHIMOMURA
C   95-05-05  LILLY  CONVRT SUBROUTINE TO FORTRAN 77
C 1999-12-21  KRISHNA KUMAR CONVERTED THIS CODE FROM CRAY TO IBM SP
C
C USAGE:  CALL NPOLUV(FULOLA, FVLOLA, IMAX, JMAX, IEXIT)
C   INPUT ARGUMENTS:
C     (1)FULOLA... REAL   FULOLA(IMAX,JMAX) IS FIELD OF U-COMPONENTS
C                  ON LOLA GRID
C     (2)FVLOLA... REAL   FVLOLA(IMAX,JMAX) IS FIELD OF V-COMPONENTS
C                  ON LOLA GRID.
C     (3)IMAX  ... I-DIMENSION OF LOLA GRID
C                  IN WHICH X-AXIS PARALLELS EQUATOR WITH ORIGIN AT
C                  GREENWICH MERIDIAN AT I=1, WITH GREENWICH REPEATED
C                  AT I=IMAX
C     (4)JMAX  ... J-DIMENSION OF LOLA GRID
C                  IN WHICH J=1 IS AT EQUATOR, AND
C                  ROW J=JMAX IS AT NORTH POLE.
C
C   OUTPUT ARGUMENTS:
C     (5)IEXIT ... RETURN CODE
C
C   RETURN CONDITIONS:
C     IEXIT=0  IS NORMAL RETURN,
C     IEXIT=1  IS ERROR RETURN DUE TO BAD VALUE  GIVEN FOR IMAX/JMAX
C
C   REMARKS: RESULTS WILL OVERSTORE J=JMAX ROW IN GIVEN FIELDS.
C     THIS ROUTINE IS A CRUTCH TO BE USED TEMPORARILY
C     UNTIL U & V FIELDS ON LOLA GRID ARE GENERATED WITH GOOD DATA
C     IN POLE ROW.
C     FOR AN EXAMPLE OF THIS SAME LOGIC SEE CRISSMAN'S SUBR POLUVN
C     USED IN PROGRAM ATATRAN.
C     SEE RUSS JONES, W3421, FOR STATUS OF LOLA GRID DATA.
C
C ATTRIBUTES:
C     LANGUAGE: F90      
C     MACHINE : IBM                                   
C
C$$$
C
      DIMENSION  FULOLA(IMAX,JMAX)
      DIMENSION  FVLOLA(IMAX,JMAX)
C
      DATA     CNV2RA / 0.0174533 /
C
      IEXIT = 0
      IMAXM1 = IMAX - 1
      IF(IMAXM1 .LE. 0) GO TO 900
      JMAXM1 = JMAX - 1
      IF(JMAXM1 .LE. 0) GO TO 900
      DEGPGI = 360.0 / FLOAT(IMAXM1)
C     ... WORK WITH WIND DATA FROM ONE ROW BELOW POLE ROW,
C     ...   ROTATING TO ONE ORIENTATION, THEN SUMMING THEM...
      USUM = 0.0
      VSUM = 0.0
      DO  222  I = 1,IMAXM1
      ELONG = FLOAT(I-1) * DEGPGI
      ELR = ELONG * CNV2RA
      SINELR = SIN(ELR)
      COSELR = COS(ELR)
      USUM = USUM + FULOLA(I,JMAXM1)*COSELR - FVLOLA(I,JMAXM1)*SINELR
      VSUM = VSUM + FULOLA(I,JMAXM1)*SINELR + FVLOLA(I,JMAXM1)*COSELR
  222 CONTINUE
C     ... THEN, GET AVERAGE AT THAT STD MERIDIAN
      UAVG = USUM / FLOAT(IMAXM1)
      VAVG = VSUM / FLOAT(IMAXM1)
C     ... THEN, ROTATE TO INDIVIDUAL MERIDIANS AND STASH IN POLE ROW
      DO  333  I = 1,IMAXM1
      ELONG = FLOAT(I-1) * DEGPGI
      ELR = ELONG * CNV2RA
      SINELR = SIN(ELR)
      COSELR = COS(ELR)
      FULOLA(I,JMAX) = UAVG*COSELR + VAVG * SINELR
      FVLOLA(I,JMAX) = -UAVG * SINELR + VAVG * COSELR
  333 CONTINUE
      FULOLA(IMAX,JMAX) = FULOLA(1,JMAX)
      FVLOLA(IMAX,JMAX) = FVLOLA(1,JMAX)
C     ... WHICH FILLS THE REPEATED GREENWICH MERIDIAN NORTH POLE PT
      GO TO 999
  900 CONTINUE
C     ... COMES HERE FOR ERROR EXIT. IMAX/JMAX OUT-OF-RANGE
      IEXIT = 1
      GO TO 999
C
  999 CONTINUE
      RETURN
      END
