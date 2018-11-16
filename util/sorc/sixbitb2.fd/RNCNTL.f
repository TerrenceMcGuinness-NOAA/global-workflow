      SUBROUTINE RNCNTL(NMAPS,IDATC,IOPN,ISWTCH,KRUN1,ITOUT1,ICYC1,
     1                  INOPN1,INOPN2,INOPNA,INOPNB)
C  $$$  SUBPROGRAM DOCUMENTATION BLOCK
C                .      .    .                                       .
C SUBPROGRAM:    RNCNTL      INPUT FIELD READER
C   PRGMMR: LILLY            ORG: W/NMC412   DATE: 95-05-05
C
C ABSTRACT: READS IN THE BASIC JOB RUN.
C
C PROGRAM HISTORY LOG:
C   ??-??-??  DICK SCHURR
C   91-02-21  STEVE LILLY, MODIFIED ROUTINE AND ADDED DOC BLOCK.
C   95-05-05  LILLY  CONVRTY SUBROUTINE TO FORTRAN 77.
C
C USAGE:    CALL RNCNTL(NMAPS,IDATC,IOPN,ISWTCH,KRUN1,ITOUT1,ICYCL1,
C                       INOPN1,INOPN2,INOPNA,INOPNB)
C   INPUT ARGUMENT LIST:
C     INARG1   - GENERIC DESCRIPTION, INCLUDING CONTENT, UNITS,
C     INARG2   - TYPE.  EXPLAIN FUNCTION IF CONTROL VARIABLE.
C
C   OUTPUT ARGUMENT LIST:      (INCLUDING WORK ARRAYS)
C     WRKARG   - GENERIC DESCRIPTION, ETC., AS ABOVE.
C     OUTARG1  - EXPLAIN COMPLETELY IF ERROR RETURN
C     ERRFLAG  - EVEN IF MANY LINES ARE NEEDED
C
C   INPUT FILES:   (DELETE IF NO INPUT FILES IN SUBPROGRAM)
C     DDNAME1  - GENERIC NAME & CONTENT
C
C   OUTPUT FILES:  (DELETE IF NO OUTPUT FILES IN SUBPROGRAM)
C     DDNAME2  - GENERIC NAME & CONTENT AS ABOVE
C     FT06F001 - INCLUDE IF ANY PRINTOUT
C
C REMARKS: LIST CAVEATS, OTHER HELPFUL HINTS OR INFORMATION
C
C ATTRIBUTES:
C   LANGUAGE: CF77       
C   MACHINE:  CRAY4
C
C$$$
C
      DIMENSION LKRUN(3,4)
      DIMENSION LICYL(2,2)
      DIMENSION LITOUT(3,4)
      DIMENSION ICODES(3,6)
      DIMENSION JCODES(2,6)
C
      DATA      NKRUN/4/
C     ...RUN TYPE CONTROL TABLE
C
      DATA      LKRUN/4HOPNL,1H ,1,4HOPNL,1HB,2,4HCOUT,1HD,3,4HCOUT,1HT,
     1               4/
C
C     ...OUTPUT CYCLE CONTROL TABLE
C
      DATA    LICYL/3H00Z,1,3H12Z,2/
      DATA    NITOUT/4/
C
C     ...OUTPUT TAU CONTROL TABLE
C
      DATA    LITOUT/4H1824,1HH,1,4H3036,1HH,2,4HALL ,1H ,3,4H2448,1HH,4
     1     /
      DATA     NICYL/2/
      DATA     NMAPM/100/
      DATA     NOPCDS/6/
      DATA     ICODES/4HOPN0,1H9,1,4HOPN1,1H0,2,4HOPN2,1H5,3,4HOPN2,1H6,
     1        4,4HOPN2,1H8,5,4HOPN3,1H3,6/
      DATA    JCODES/4HJ080,1H4,4HJ082,1H4,4HJ087,1H4,4HJ999,1H8,
     +               4HJ999,1H9,4HJ999,1H9/
C     ...THIS SUBROUTINE READS IN THE BASIC JOB RUN
C     ...CONTROLS AND CHECKS THEM FOR PROPER CLASSIFICATIONS
C
C     ...INPUT CONTROLS
C     (1)      KRUNA,KRUNB   (A4,A1)
C     WHERE         KRUN=1   OPNL 18/24 OR 24/48 RUN
C                  2    OPNL 30/36 RUN BACKUP
C                  3    CHECKOUT RUN(DISK)
C                  4    CHECKOUT RUN(TAPE)
C   (2)  ITOUTA,ITOUTB  (A4,A1)
C   WHERE    ITOUT=1    OUTPUT 18/24 HR REGULAR
C                  2    OUTPUT 30/36 HR BACKUP
C                  3    ALL
C                  4    OUTPUT 24/48 HR REGULAR
C   (3)  ICYCLA,ICYCLB  (A4,A1)
C   WHERE   ICYCLE=1   00Z
C212
C
C   (4)  NMAPS       (I5)
C   WHERE    NMAPS=NO. OF MAPS TO BE PROCESSED
C
C   (5)  IDATC       (I5)
C   WHERE    IDATC=0    NO DATE/TIME TEST
C                  1    DATE/TIME TEST
C   (6)  IOPN        (I5)
C   WHERE    IOPN=0     CHECKOUT RUN
C                 1     OPERATIONAL RUN
C
C   (7)  INTAPE      (I5)
C   WHERE  INTAPE=0     INPUT FROM DISK-OPERATIONAL
C                 1     INPUT SPECTRAL FILES FROM TAPE
C
C   (8)  INOPNA,INOPNB (A4,A1)
C   WHERE    INOPN=     OPERATIONAL JOB TYPE
C
C   (9)  ISWTCH=0       INPUT SCHEDULE CONTROLS FROM CARDS
C               1       INPUT SCHEDULE CONTROLS FORM DISK
C
C     ...BASIC JOB RUN CONTROLS (SET FOR EACH JOB)
C
C
C
C??   READ 5500,KRUNA,KRUNB,ITOUTA,ITOUTB,ICYCLA,ICYCLB,NMAPS,IDATC,
C     READ(5,550)KRUNA,KRUNB,ITOUTA,ITOUTB,ICYCLA,ICYCLB,NMAPS,IDATC,
c
c      open(15,file='sixbitb.generic.f15')
c
      READ(15,550)KRUNA,KRUNB,ITOUTA,ITOUTB,ICYCLA,ICYCLB,NMAPS,IDATC,
     1          IOPN,INTAPE,INOPNA,INOPNB,ISWTCH
  550 FORMAT(3(A4,A1),4I5,A4,A1,I5)
C5550 FORMAT(3(A4,A1),4I5,A4,A1,I5)
Corig PRINT 5509
      WRITE(6,5509)
 5509 FORMAT('1BASIC JOB RUN CONTROLS (SET FOR EACH JOB)')
Corig PRINT 5510, KRUNA,KRUNB,ITOUTA,ITOUTB,ICYCLA,ICYCLB,NMAPS
      WRITE(6,5510) KRUNA,KRUNB,ITOUTA,ITOUTB,ICYCLA,ICYCLB,NMAPS
 5510 FORMAT('0OPERATIONAL RUN TYPE=  ',A4,A1,'  OUTPUT TAU=  ',A4,A1,'
     1RUN CYCLE=  ',A4,A1,'  NUMBER OF MAPS=  ',I5)
Corig PRINT 5511,IDATC,IOPN,INTAPE
      WRITE(6,5511) IDATC,IOPN,INTAPE
 5511 FORMAT('0DATE CHECK=  ',I5,'  OPERATIONAL FLAG=  ',I5,'  INPUT TAP
     1E FLAG=  ',I5)
Corig PRINT 5513,ISWTCH,INOPNA,INOPNB
      WRITE(6,5513) ISWTCH,INOPNA,INOPNB
 5513 FORMAT('0INPUT SCHEDULE CONTROL SWITCH=  ',I5,'  OPNL JOB TYPE=  '
     1,A4,A1)
      DO 5550 IK=1,NKRUN
      IF((KRUNA.NE.LKRUN(1,IK)).OR.(KRUNB.NE.LKRUN(2,IK))) GO TO 5550
      KRUN1=LKRUN(3,IK)
      GO TO 5553
 5550 CONTINUE
Corig PRINT 5540
      WRITE(6,5540)
 5540 FORMAT('0ERROR ON CONTROL INPUT CARD FOR KRUN-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 541
 5553 CONTINUE
      DO 5555 IK=1,NITOUT
      IF((ITOUTA.NE.LITOUT(1,IK)).OR.(ITOUTB.NE.LITOUT(2,IK))) GO TO
     15555
      ITOUT1=LITOUT(3,IK)
      GO TO 5560
 5555 CONTINUE
Corig PRINT 5543
      WRITE(6,5543)
 5543 FORMAT('0ERROR ON CONTROL INPUT CARD FOR ITOUT-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 544
 5560 CONTINUE
      DO 5565 IK=1,NICYL
      IF(ICYCLA.NE.LICYL(1,IK)) GO TO 5565
      ICYC1=LICYL(2,IK)
      GO TO 5570
 5565 CONTINUE
Corig PRINT 5545
      WRITE(6,5545)
 5545 FORMAT('0ERROR ON CONTROL INPUT CARD FOR ICYCLE-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 546
 5570 CONTINUE
      IF((NMAPS.LE.NMAPM).AND.(NMAPS.GT.0)) GO TO 5575
Corig PRINT 5547
      WRITE(6,5547)
 5547 FORMAT('0ERROR ON CONTROL INPUT CARD FOR NMAPS-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 552
 5575 CONTINUE
      IF((IDATC.EQ.0).OR.(IDATC.EQ.1)) GO TO 5620
      WRITE(6,5600)
 5600 FORMAT('0ERROR ON CONTROL INPUT CARD FOR IDATC-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 601
 5620 CONTINUE
      IF((IOPN.EQ.0).OR.(IOPN.EQ.1)) GO TO 5630
Corig PRINT5602
      WRITE(6,5602)
 5602 FORMAT('0ERROR ON CONTROL INPUT CARD FOR IOPN-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 603
 5630 CONTINUE
      IF((INTAPE.GT.-1).AND.(INTAPE.LE.1)) GO TO 5640
Corig PRINT 5604
      WRITE(6,5604)
 5604 FORMAT('0ERROR ON CONTROL INPUT CARD FOR INTAPE-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 605
 5640 CONTINUE
      IF((ISWTCH.GT.-1).AND.(ISWTCH.LE.1)) GO TO 5650
Corig PRINT 5606
      WRITE(6,5606)
 5606 FORMAT('0ERROR ON CONTROL INPUT CARD FOR ISWTCH-FIX THEN RSTART')
      CALL W3TAGE('SIXBITB2')
      STOP 607
 5650 CONTINUE
      DO 5651 IK=1,NOPCDS
      IF((INOPNA.NE.ICODES(1,IK)).OR.(INOPNB.NE.ICODES(2,IK))) GO TO
     15651
      INOP=ICODES(3,IK)
      INOPN1=JCODES(1,INOP)
      INOPN2=JCODES(2,INOP)
      GO TO 5654
 5651 CONTINUE
Corig PRINT 5652
      WRITE(6,5652)
 5652 FORMAT('0ERROR ON CONTROL INPUT CARD FOR INOPN-FIX THEN RESTART')
      CALL W3TAGE('SIXBITB2')
      STOP 653
 5654 CONTINUE
      RETURN
      END
